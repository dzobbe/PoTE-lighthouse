//! Provides the `Eth2NetworkConfig` struct which defines the configuration of an eth2 network or
//! test-network (aka "testnet").
//!
//! Whilst the `Eth2NetworkConfig` struct can be used to read a specification from a directory at
//! runtime, this crate also includes some pre-defined network configurations "built-in" to the
//! binary itself (the most notable of these being the "mainnet" configuration). When a network is
//! "built-in", the  genesis state and configuration files is included in the final binary via the
//! `std::include_bytes` macro. This provides convenience to the user, the binary is self-sufficient
//! and does not require the configuration to be read from the filesystem at runtime.
//!
//! To add a new built-in testnet, add it to the `define_hardcoded_nets` invocation in the `eth2_config`
//! crate.

use bytes::Bytes;
use discv5::enr::{CombinedKey, Enr};
use eth2_config::{HardcodedNet, instantiate_hardcoded_nets};
use kzg::trusted_setup::get_trusted_setup;
use pretty_reqwest_error::PrettyReqwestError;
use reqwest::{Client, Error};
use sensitive_url::SensitiveUrl;
use sha2::{Digest, Sha256};
use std::fs::{File, create_dir_all};
use std::io::{Read, Write};
use std::path::PathBuf;
use std::str::FromStr;
use std::time::Duration;
use tracing::{debug, info, warn};
use types::{BeaconBlockHeader, BeaconState, ChainSpec, Config, EthSpec, EthSpecId, Fork, Hash256, Slot};
use url::Url;
use ssz::{DecodeError, Encode};

pub use eth2_config::GenesisStateSource;

pub const DEPLOY_BLOCK_FILE: &str = "deposit_contract_block.txt";
pub const BOOT_ENR_FILE: &str = "bootstrap_nodes.yaml";
pub const GENESIS_STATE_FILE: &str = "genesis.ssz";
pub const BASE_CONFIG_FILE: &str = "config.yaml";

// Creates definitions for:
//
// - Each of the `HardcodedNet` values (e.g., `MAINNET`, `HOLESKY`, etc).
// - `HARDCODED_NETS: &[HardcodedNet]`
// - `HARDCODED_NET_NAMES: &[&'static str]`
instantiate_hardcoded_nets!(eth2_config);

pub const DEFAULT_HARDCODED_NETWORK: &str = "mainnet";

/// A simple slice-or-vec enum to avoid cloning the beacon state bytes in the
/// binary whilst also supporting loading them from a file at runtime.
#[derive(Clone, PartialEq, Debug)]
pub enum GenesisStateBytes {
    Slice(&'static [u8]),
    Vec(Vec<u8>),
}

impl AsRef<[u8]> for GenesisStateBytes {
    fn as_ref(&self) -> &[u8] {
        match self {
            GenesisStateBytes::Slice(slice) => slice,
            GenesisStateBytes::Vec(vec) => vec.as_ref(),
        }
    }
}

impl From<&'static [u8]> for GenesisStateBytes {
    fn from(slice: &'static [u8]) -> Self {
        GenesisStateBytes::Slice(slice)
    }
}

impl From<Vec<u8>> for GenesisStateBytes {
    fn from(vec: Vec<u8>) -> Self {
        GenesisStateBytes::Vec(vec)
    }
}

/// Specifies an Eth2 network.
///
/// See the crate-level documentation for more details.
#[derive(Clone, PartialEq, Debug)]
pub struct Eth2NetworkConfig {
    /// Note: instead of the block where the contract is deployed, it is acceptable to set this
    /// value to be the block number where the first deposit occurs.
    pub deposit_contract_deploy_block: u64,
    pub boot_enr: Option<Vec<Enr<CombinedKey>>>,
    pub genesis_state_source: GenesisStateSource,
    pub genesis_state_bytes: Option<GenesisStateBytes>,
    pub config: Config,
    pub kzg_trusted_setup: Vec<u8>,
}

impl Eth2NetworkConfig {
    /// When Lighthouse is built it includes zero or more "hardcoded" network specifications. This
    /// function allows for instantiating one of these nets by name.
    pub fn constant(name: &str) -> Result<Option<Self>, String> {
        HARDCODED_NETS
            .iter()
            .find(|net| net.name == name)
            .map(Self::from_hardcoded_net)
            .transpose()
    }

    /// Instantiates `Self` from a `HardcodedNet`.
    fn from_hardcoded_net(net: &HardcodedNet) -> Result<Self, String> {
        let config: Config = serde_yaml::from_reader(net.config)
            .map_err(|e| format!("Unable to parse yaml config: {:?}", e))?;
        let kzg_trusted_setup = get_trusted_setup();
        Ok(Self {
            deposit_contract_deploy_block: serde_yaml::from_reader(net.deploy_block)
                .map_err(|e| format!("Unable to parse deploy block: {:?}", e))?,
            boot_enr: Some(
                serde_yaml::from_reader(net.boot_enr)
                    .map_err(|e| format!("Unable to parse boot enr: {:?}", e))?,
            ),
            genesis_state_source: net.genesis_state_source,
            genesis_state_bytes: Some(net.genesis_state_bytes)
                .filter(|bytes| !bytes.is_empty())
                .map(Into::into),
            config,
            kzg_trusted_setup,
        })
    }

    /// Returns an identifier that should be used for selecting an `EthSpec` instance for this
    /// network configuration.
    pub fn eth_spec_id(&self) -> Result<EthSpecId, String> {
        self.config
            .eth_spec_id()
            .ok_or_else(|| "Config does not match any known preset".to_string())
    }

    /// Returns `true` if this configuration contains a `BeaconState`.
    pub fn genesis_state_is_known(&self) -> bool {
        self.genesis_state_source != GenesisStateSource::Unknown
    }

    /// The `genesis_validators_root` of the genesis state.
    pub fn genesis_validators_root<E: EthSpec>(&self) -> Result<Option<Hash256>, String> {
        if let GenesisStateSource::Url {
            genesis_validators_root,
            ..
        } = self.genesis_state_source
        {
            Hash256::from_str(genesis_validators_root)
                .map(Option::Some)
                .map_err(|e| {
                    format!(
                        "Unable to parse genesis state genesis_validators_root: {:?}",
                        e
                    )
                })
        } else {
            self.get_genesis_state_from_bytes::<E>()
                .map(|state| Some(state.genesis_validators_root()))
        }
    }

    /// Get the genesis state root for this network.
    ///
    /// `Ok(None)` will be returned if the genesis state is not known. No network requests will be
    /// made by this function. This function will not error unless the genesis state configuration
    /// is corrupted.
    pub fn genesis_state_root<E: EthSpec>(&self) -> Result<Option<Hash256>, String> {
        match self.genesis_state_source {
            GenesisStateSource::Unknown => Ok(None),
            GenesisStateSource::Url {
                genesis_state_root, ..
            } => Hash256::from_str(genesis_state_root)
                .map(Option::Some)
                .map_err(|e| format!("Unable to parse genesis state root: {:?}", e)),
            GenesisStateSource::IncludedBytes => {
                self.get_genesis_state_from_bytes::<E>()
                    .and_then(|mut state| {
                        Ok(Some(
                            state
                                .canonical_root()
                                .map_err(|e| format!("Hashing error: {e:?}"))?,
                        ))
                    })
            }
        }
    }

    /// Construct a consolidated `ChainSpec` from the YAML config.
    pub fn chain_spec<E: EthSpec>(&self) -> Result<ChainSpec, String> {
        ChainSpec::from_config::<E>(&self.config).ok_or_else(|| {
            format!(
                "YAML configuration incompatible with spec constants for {}",
                E::spec_name()
            )
        })
    }

    /// Attempts to deserialize `self.beacon_state`, returning an error if it's missing or invalid.
    ///
    /// If the genesis state is configured to be downloaded from a URL, then the
    /// `genesis_state_url` will override the built-in list of download URLs.
    pub async fn genesis_state<E: EthSpec>(
        &self,
        genesis_state_url: Option<&str>,
        timeout: Duration,
    ) -> Result<Option<BeaconState<E>>, String> {
        let spec = self.chain_spec::<E>()?;
        match &self.genesis_state_source {
            GenesisStateSource::Unknown => Ok(None),
            GenesisStateSource::IncludedBytes => {
                let state = self.get_genesis_state_from_bytes()?;
                Ok(Some(state))
            }
            GenesisStateSource::Url {
                urls: built_in_urls,
                checksum,
                genesis_validators_root,
                ..
            } => {
                let checksum = Hash256::from_str(checksum).map_err(|e| {
                    format!("Unable to parse genesis state bytes checksum: {:?}", e)
                })?;
                let bytes = if let Some(specified_url) = genesis_state_url {
                    download_genesis_state(&[specified_url], timeout, checksum).await
                } else {
                    download_genesis_state(built_in_urls, timeout, checksum).await
                }?;
                let state = BeaconState::from_ssz_bytes(bytes.as_ref(), &spec).map_err(|e| {
                    format!("Downloaded genesis state SSZ bytes are invalid: {:?}", e)
                })?;

                let genesis_validators_root =
                    Hash256::from_str(genesis_validators_root).map_err(|e| {
                        format!(
                            "Unable to parse genesis state genesis_validators_root: {:?}",
                            e
                        )
                    })?;
                if state.genesis_validators_root() != genesis_validators_root {
                    return Err(format!(
                        "Downloaded genesis validators root {:?} does not match expected {:?}",
                        state.genesis_validators_root(),
                        genesis_validators_root
                    ));
                }

                Ok(Some(state))
            }
        }
    }

    fn get_genesis_state_from_bytes<E: EthSpec>(&self) -> Result<BeaconState<E>, String> {
        let spec = self.chain_spec::<E>()?;

        self.genesis_state_bytes
            .as_ref()
            .map(|bytes| {
                let bytes_ref = bytes.as_ref();

                // Extra debugging to help diagnose OffsetIntoFixedPortion and similar SSZ errors.
                // This logs which network/config is being used and the expected fork at genesis.
                let config_name = self
                    .config
                    .config_name
                    .clone()
                    .unwrap_or_else(|| "<unknown>".to_string());
                let eth_spec_id = self
                    .eth_spec_id()
                    .map(|id| id.to_string())
                    .unwrap_or_else(|_| "<unknown>".to_string());
                let genesis_fork = spec.fork_name_at_slot::<E>(Slot::new(0));

                // Log fork configuration to verify which fork is active
                let fork_epochs = format!(
                    "altair={:?}, bellatrix={:?}, capella={:?}, deneb={:?}, electra={:?}, fulu={:?}, gloas={:?}",
                    spec.altair_fork_epoch,
                    spec.bellatrix_fork_epoch,
                    spec.capella_fork_epoch,
                    spec.deneb_fork_epoch,
                    spec.electra_fork_epoch,
                    spec.fulu_fork_epoch,
                    spec.gloas_fork_epoch,
                );

                // Determine genesis source
                let genesis_source = match &self.genesis_state_source {
                    GenesisStateSource::IncludedBytes => {
                        match &self.genesis_state_bytes {
                            Some(GenesisStateBytes::Slice(_)) => "built-in (compiled into binary)",
                            Some(GenesisStateBytes::Vec(_)) => "file (loaded from testnet directory)",
                            None => "unknown",
                        }
                    }
                    GenesisStateSource::Url { .. } => "URL (downloaded)",
                    GenesisStateSource::Unknown => "unknown",
                };

                info!(
                    bytes_len = bytes_ref.len(),
                    %config_name,
                    %eth_spec_id,
                    preset_base = %self.config.preset_base,
                    ?genesis_fork,
                    genesis_source = %genesis_source,
                    fork_epochs = %fork_epochs,
                    "Decoding genesis state from bytes",
                );

                // Log first few bytes for debugging (without hex encoding to avoid extra dependency)
                if bytes_ref.len() > 100 {
                    debug!(
                        first_bytes_len = 100,
                        total_bytes_len = bytes_ref.len(),
                        "Genesis state preview (first 100 bytes logged)",
                    );
                }

                // Log SSZ structure information before decoding
                // Calculate expected fixed portion sizes
                use ssz::Decode;
                let expected_header_size = <BeaconBlockHeader as Decode>::ssz_fixed_len();
                let genesis_time_len = <u64 as Decode>::ssz_fixed_len();
                let genesis_validators_root_len = <Hash256 as Decode>::ssz_fixed_len();
                let slot_len = <Slot as Decode>::ssz_fixed_len();
                let fork_len = <Fork as Decode>::ssz_fixed_len();
                
                // Calculate where the header should start in the fixed portion
                let header_start_offset = genesis_time_len + genesis_validators_root_len + slot_len + fork_len;
                
                // Try to extract header size from SSZ bytes if possible
                let actual_header_size_in_bytes = if bytes_ref.len() > header_start_offset + expected_header_size {
                    // We can't directly read the header size without decoding, but we can log the expected position
                    Some(expected_header_size)
                } else {
                    None
                };
                
                info!(
                    total_bytes = bytes_ref.len(),
                    expected_header_fixed_len = expected_header_size,
                    expected_tee_header_size = 8305,
                    expected_standard_header_size = 112,
                    header_start_offset = header_start_offset,
                    genesis_time_len = genesis_time_len,
                    genesis_validators_root_len = genesis_validators_root_len,
                    slot_len = slot_len,
                    fork_len = fork_len,
                    actual_header_size_in_bytes = ?actual_header_size_in_bytes,
                    "Starting genesis state SSZ decoding - header size analysis",
                );
                
                // Log the expected fixed portion calculation
                info!(
                    expected_fixed_portion_before_header = header_start_offset,
                    expected_header_size = expected_header_size,
                    expected_fixed_portion_after_header = header_start_offset + expected_header_size,
                    "Expected SSZ fixed portion calculation (Lighthouse expects {} byte header)",
                    expected_header_size
                );
                
                // Try to peek at the header bytes to see what size it actually is
                if bytes_ref.len() >= header_start_offset + 112 {
                    // Check if it looks like a 112-byte header (standard) or 8305-byte header (TEE)
                    let header_end_112 = header_start_offset + 112;
                    let header_end_8305 = header_start_offset + 8305;
                    
                    if bytes_ref.len() >= header_end_112 {
                        let header_bytes_112 = &bytes_ref[header_start_offset..header_end_112];
                        debug!(
                            header_start_offset = header_start_offset,
                            header_bytes_112_len = header_bytes_112.len(),
                            "Peeked at first 112 bytes of header position"
                        );
                    }
                    
                    if bytes_ref.len() >= header_end_8305 {
                        let header_bytes_8305 = &bytes_ref[header_start_offset..header_end_8305];
                        info!(
                            header_start_offset = header_start_offset,
                            header_bytes_8305_len = header_bytes_8305.len(),
                            "Peeked at full 8305 bytes of header position - header appears to be TEE-sized in SSZ bytes"
                        );
                    } else {
                        warn!(
                            header_start_offset = header_start_offset,
                            bytes_available_after_header_start = bytes_ref.len() - header_start_offset,
                            expected_tee_header_size = 8305,
                            expected_standard_header_size = 112,
                            "Not enough bytes for TEE header (8305 bytes) at expected position - might be standard 112-byte header"
                        );
                    }
                } else {
                    warn!(
                        header_start_offset = header_start_offset,
                        total_bytes = bytes_ref.len(),
                        "Not enough bytes to reach header start position - SSZ structure might be malformed"
                    );
                }
                
                // Analyze offset values in the SSZ structure to detect mismatches
                // SSZ stores offsets as 4-byte little-endian values after fixed-length fields
                // For BeaconState, offsets start after ALL fixed-length fields including BlockRoots and StateRoots
                // Fixed portion: genesis_time(8) + genesis_validators_root(32) + slot(8) + fork(16) + header(variable) + BlockRoots(8192*32) + StateRoots(8192*32)
                let block_roots_size = 8192 * 32; // 262144
                let state_roots_size = 8192 * 32; // 262144
                let expected_fixed_portion_end = header_start_offset + expected_header_size + block_roots_size + state_roots_size;
                if bytes_ref.len() > expected_fixed_portion_end + 4 {
                    // Read first few offset values to see what they point to
                    // SSZ offsets are 4-byte little-endian u32 values
                    let mut offset_values = Vec::new();
                    for i in 0..10.min((bytes_ref.len() - expected_fixed_portion_end) / 4) {
                        let offset_pos = expected_fixed_portion_end + i * 4;
                        if offset_pos + 4 <= bytes_ref.len() {
                            let offset_bytes = [
                                bytes_ref[offset_pos],
                                bytes_ref[offset_pos + 1],
                                bytes_ref[offset_pos + 2],
                                bytes_ref[offset_pos + 3],
                            ];
                            let offset_val = u32::from_le_bytes(offset_bytes) as usize;
                            offset_values.push((offset_pos, offset_val));
                        }
                    }
                    
                    info!(
                        expected_fixed_portion_end = expected_fixed_portion_end,
                        first_offset_position = expected_fixed_portion_end,
                        offset_values = ?offset_values.iter().take(5).map(|(pos, val)| format!("pos={}, val={}", pos, val)).collect::<Vec<_>>(),
                        "SSZ offset values analysis - checking if offsets point beyond fixed portion"
                    );
                    
                    // Check if any offsets point into the fixed portion
                    for (offset_pos, offset_val) in &offset_values {
                        if *offset_val < expected_fixed_portion_end {
                            let possible_standard_fixed_end = header_start_offset + 112 + block_roots_size + state_roots_size;
                            let would_be_valid_with_standard = *offset_val >= possible_standard_fixed_end;
                            
                            warn!(
                                offset_position = offset_pos,
                                offset_value = offset_val,
                                expected_fixed_portion_end = expected_fixed_portion_end,
                                possible_standard_fixed_end = possible_standard_fixed_end,
                                would_be_valid_with_standard_header = would_be_valid_with_standard,
                                "⚠️  OFFSET MISMATCH: Offset at position {} has value {} which points INTO fixed portion (ends at {}). With standard {} byte header, fixed portion would end at {}, and this offset would be {}",
                                offset_pos, offset_val, expected_fixed_portion_end, 112, possible_standard_fixed_end,
                                if would_be_valid_with_standard { "VALID" } else { "STILL INVALID" }
                            );
                            
                            // Special case: offset 0 often means "empty list starts immediately after fixed portion"
                            if *offset_val == 0 {
                                warn!(
                                    "🔍 CRITICAL FINDING: Offset value is 0 at position {}. In SSZ, offset 0 typically means variable-length data starts immediately after fixed portion. Genesis generator likely calculated this assuming fixed portion ends at {} (with {} byte header), but Lighthouse expects {} (with {} byte header). Difference: {} bytes",
                                    offset_pos, possible_standard_fixed_end, 112, expected_fixed_portion_end, expected_header_size,
                                    expected_fixed_portion_end - possible_standard_fixed_end
                                );
                            }
                        } else {
                            debug!(
                                offset_position = offset_pos,
                                offset_value = offset_val,
                                expected_fixed_portion_end = expected_fixed_portion_end,
                                "✅ Offset correctly points beyond fixed portion"
                            );
                        }
                    }
                    
                    // Calculate what fixed portion size the genesis generator might have used
                    // If offsets are pointing to locations that suggest a different fixed portion size
                    if let Some((_, first_offset_val)) = offset_values.first() {
                        let possible_standard_fixed_end = header_start_offset + 112 + block_roots_size + state_roots_size;
                        if *first_offset_val == possible_standard_fixed_end {
                            warn!(
                                first_offset_value = first_offset_val,
                                possible_standard_fixed_end = possible_standard_fixed_end,
                                expected_fixed_portion_end = expected_fixed_portion_end,
                                "🔍 GENESIS GENERATOR ANALYSIS: First offset points to {}, suggesting genesis generator used {} byte header (standard) instead of {} byte header (TEE)",
                                first_offset_val, 112, expected_header_size
                            );
                        } else if *first_offset_val >= expected_fixed_portion_end {
                            info!(
                                first_offset_value = first_offset_val,
                                expected_fixed_portion_end = expected_fixed_portion_end,
                                "✅ First offset correctly points beyond fixed portion (ends at {})",
                                expected_fixed_portion_end
                            );
                        }
                    }
                    
                    // The error says offset 2736713 points into fixed portion
                    // This means at position 2736713, there's an offset value that's < 8369
                    // Let's check what offset value is stored around that position
                    let error_offset_position = 2736713;
                    if error_offset_position < bytes_ref.len() {
                        // Check offset values near the error position
                        let check_start = error_offset_position.saturating_sub(20).max(expected_fixed_portion_end);
                        let check_end = (error_offset_position + 20).min(bytes_ref.len());
                        
                        warn!(
                            error_offset_position = error_offset_position,
                            checking_range_start = check_start,
                            checking_range_end = check_end,
                            expected_fixed_portion_end = expected_fixed_portion_end,
                            "🔍 ERROR OFFSET ANALYSIS: Checking offset values near error position {}",
                            error_offset_position
                        );
                        
                        // Read offset values in this range
                        let mut error_range_offsets = Vec::new();
                        for pos in (check_start..check_end).step_by(4) {
                            if pos + 4 <= bytes_ref.len() {
                                let offset_bytes = [
                                    bytes_ref[pos],
                                    bytes_ref[pos + 1],
                                    bytes_ref[pos + 2],
                                    bytes_ref[pos + 3],
                                ];
                                let offset_val = u32::from_le_bytes(offset_bytes) as usize;
                                error_range_offsets.push((pos, offset_val));
                                
                                // Check if this offset points into fixed portion
                                if offset_val < expected_fixed_portion_end && offset_val > 0 {
                                    warn!(
                                        offset_position = pos,
                                        offset_value = offset_val,
                                        expected_fixed_portion_end = expected_fixed_portion_end,
                                        distance_from_error_pos = error_offset_position.saturating_sub(pos),
                                        "⚠️  FOUND PROBLEMATIC OFFSET: At position {} ({} bytes before error), offset value {} points INTO fixed portion (ends at {})",
                                        pos, error_offset_position.saturating_sub(pos), offset_val, expected_fixed_portion_end
                                    );
                                }
                            }
                        }
                        
                        info!(
                            error_range_offsets = ?error_range_offsets.iter().map(|(pos, val)| format!("pos={}, val={}", pos, val)).collect::<Vec<_>>(),
                            "Offset values near error position"
                        );
                    }
                }

                match BeaconState::from_ssz_bytes(bytes_ref, &spec) {
                    Ok(state) => {
                        // Verify TEE fields by checking the latest block header if available
                        let latest_block_header = state.latest_block_header();
                        let header_size = latest_block_header.as_ssz_bytes().len();
                        
                        info!(
                            "🔍 Genesis block header size: {} bytes (expected TEE: 8305, standard: 112)",
                            header_size
                        );
                        info!(
                            header_size = header_size,
                            expected_tee_header_size = 8305,
                            expected_standard_header_size = 112,
                            header_slot = latest_block_header.slot.as_u64(),
                            header_proposer_index = latest_block_header.proposer_index,
                            "Latest block header size check (TEE header should be ~8305 bytes, standard is 112)",
                        );
                        
                        // Additional validation: check if header size matches expectations
                        let expected_tee_size: usize = 8305;
                        let expected_standard_size: usize = 112;
                        if header_size != expected_tee_size && header_size != expected_standard_size {
                            warn!(
                                header_size = header_size,
                                expected_tee_header_size = 8305,
                                expected_standard_header_size = 112,
                                "Unexpected block header size - neither TEE nor standard size",
                            );
                        }
                        
                        Ok(state)
                    }
                    Err(e) => {
                        // Enhanced error logging with offset details and SSZ structure analysis
                        let error_details = match &e {
                            DecodeError::OffsetIntoFixedPortion(offset) => {
                                let offset_value: usize = *offset;
                                let bytes_len: usize = bytes_ref.len();
                                let offset_percentage = (offset_value * 100) / bytes_len.max(1);
                                let bytes_before_offset = offset_value;
                                let bytes_after_offset = bytes_len.saturating_sub(offset_value);
                                
                                // Calculate expected fixed portion with TEE header
                                let expected_fixed_start: usize = genesis_time_len + genesis_validators_root_len + slot_len + fork_len;
                                let expected_fixed_with_tee_header = expected_fixed_start + expected_header_size;
                                let expected_fixed_with_standard_header = expected_fixed_start + 112;
                                
                                // Try to analyze what might be at this offset
                                let analysis = if offset_value < bytes_len {
                                    if offset_value < expected_fixed_start {
                                        format!("Offset {} is in the initial fixed portion (before latest_block_header at offset {})", offset_value, expected_fixed_start)
                                    } else if offset_value < expected_fixed_start + expected_header_size {
                                        format!("Offset {} is within latest_block_header (header starts at offset {}, Lighthouse expects {} bytes)", offset_value, expected_fixed_start, expected_header_size)
                                    } else {
                                        format!("Offset {} is beyond the initial fixed fields (expected fixed portion end: {} with TEE header, {} with standard header)", offset_value, expected_fixed_with_tee_header, expected_fixed_with_standard_header)
                                    }
                                } else {
                                    "Offset exceeds total bytes".to_string()
                                };
                                
                                // Check if the issue is likely a header size mismatch
                                let header_size_mismatch_hint = if offset_value >= expected_fixed_start && offset_value < expected_fixed_with_tee_header {
                                    format!(
                                        "⚠️  HEADER SIZE MISMATCH DETECTED: Lighthouse expects {} byte TEE header, but genesis file might have {} byte standard header. Fixed portion mismatch: expected {} bytes (with TEE) vs {} bytes (with standard)",
                                        expected_header_size, 112, expected_fixed_with_tee_header, expected_fixed_with_standard_header
                                    )
                                } else {
                                    String::new()
                                };
                                
                                warn!(
                                    offset = offset_value,
                                    total_bytes = bytes_len,
                                    offset_percentage = offset_percentage,
                                    bytes_before_offset = bytes_before_offset,
                                    bytes_after_offset = bytes_after_offset,
                                    expected_header_size = expected_header_size,
                                    expected_fixed_start = expected_fixed_start,
                                    expected_fixed_with_tee_header = expected_fixed_with_tee_header,
                                    expected_fixed_with_standard_header = expected_fixed_with_standard_header,
                                    analysis = %analysis,
                                    header_size_mismatch_hint = %header_size_mismatch_hint,
                                    "SSZ decode error: OffsetIntoFixedPortion - detailed analysis",
                                );
                                
                                format!(
                                    "OffsetIntoFixedPortion at byte {} ({}% into {} total bytes). {}. {}",
                                    offset_value, offset_percentage, bytes_len, analysis, header_size_mismatch_hint
                                )
                            }
                            DecodeError::InvalidByteLength { len, expected } => {
                                let difference = expected.saturating_sub(*len);
                                warn!(
                                    actual_len = len,
                                    expected_len = expected,
                                    difference = difference,
                                    "SSZ decode error: InvalidByteLength",
                                );
                                format!(
                                    "InvalidByteLength: got {} bytes, expected {} bytes (difference: {})",
                                    len, expected, difference
                                )
                            }
                            _ => {
                                format!("{:?}", e)
                            }
                        };

                        warn!(
                            error = %error_details,
                            bytes_len = bytes_ref.len(),
                            %config_name,
                            %eth_spec_id,
                            preset_base = %self.config.preset_base,
                            ?genesis_fork,
                            genesis_source = %genesis_source,
                            fork_epochs = %fork_epochs,
                            "Built-in genesis state SSZ bytes failed to decode",
                        );
                        Err(format!(
                            "Built-in genesis state SSZ bytes are invalid: {}",
                            error_details
                        ))
                    }
                }
            })
            .ok_or("Genesis state bytes missing from Eth2NetworkConfig")?
    }

    /// Write the files to the directory.
    ///
    /// Overwrites files if specified to do so.
    pub fn write_to_file(&self, base_dir: PathBuf, overwrite: bool) -> Result<(), String> {
        if base_dir.exists() && !overwrite {
            return Err("Network directory already exists".to_string());
        }

        self.force_write_to_file(base_dir)
    }

    /// Write the files to the directory, even if the directory already exists.
    pub fn force_write_to_file(&self, base_dir: PathBuf) -> Result<(), String> {
        create_dir_all(&base_dir)
            .map_err(|e| format!("Unable to create testnet directory: {:?}", e))?;

        macro_rules! write_to_yaml_file {
            ($file: ident, $variable: expr) => {
                File::create(base_dir.join($file))
                    .map_err(|e| format!("Unable to create {}: {:?}", $file, e))
                    .and_then(|mut file| {
                        let yaml = serde_yaml::to_string(&$variable)
                            .map_err(|e| format!("Unable to YAML encode {}: {:?}", $file, e))?;

                        // Remove the doc header from the YAML file.
                        //
                        // This allows us to play nice with other clients that are expecting
                        // plain-text, not YAML.
                        let no_doc_header = if let Some(stripped) = yaml.strip_prefix("---\n") {
                            stripped
                        } else {
                            &yaml
                        };

                        file.write_all(no_doc_header.as_bytes())
                            .map_err(|e| format!("Unable to write {}: {:?}", $file, e))
                    })?;
            };
        }

        write_to_yaml_file!(DEPLOY_BLOCK_FILE, self.deposit_contract_deploy_block);

        if let Some(boot_enr) = &self.boot_enr {
            write_to_yaml_file!(BOOT_ENR_FILE, boot_enr);
        }

        write_to_yaml_file!(BASE_CONFIG_FILE, &self.config);

        // The genesis state is a special case because it uses SSZ, not YAML.
        if let Some(genesis_state_bytes) = &self.genesis_state_bytes {
            let file = base_dir.join(GENESIS_STATE_FILE);

            File::create(&file)
                .map_err(|e| format!("Unable to create {:?}: {:?}", file, e))
                .and_then(|mut file| {
                    file.write_all(genesis_state_bytes.as_ref())
                        .map_err(|e| format!("Unable to write {:?}: {:?}", file, e))
                })?;
        }

        Ok(())
    }

    pub fn load(base_dir: PathBuf) -> Result<Self, String> {
        macro_rules! load_from_file {
            ($file: ident) => {
                File::open(base_dir.join($file))
                    .map_err(|e| format!("Unable to open {}: {:?}", $file, e))
                    .and_then(|file| {
                        serde_yaml::from_reader(file)
                            .map_err(|e| format!("Unable to parse {}: {:?}", $file, e))
                    })?
            };
        }

        macro_rules! optional_load_from_file {
            ($file: ident) => {
                if base_dir.join($file).exists() {
                    Some(load_from_file!($file))
                } else {
                    None
                }
            };
        }

        let deposit_contract_deploy_block = load_from_file!(DEPLOY_BLOCK_FILE);
        let boot_enr = optional_load_from_file!(BOOT_ENR_FILE);
        let config = load_from_file!(BASE_CONFIG_FILE);

        // The genesis state is a special case because it uses SSZ, not YAML.
        let genesis_file_path = base_dir.join(GENESIS_STATE_FILE);
        let (genesis_state_bytes, genesis_state_source) = if genesis_file_path.exists() {
            info!(
                genesis_file = ?genesis_file_path,
                "Loading genesis state from file",
            );
            let mut bytes = vec![];
            File::open(&genesis_file_path)
                .map_err(|e| format!("Unable to open {:?}: {:?}", genesis_file_path, e))
                .and_then(|mut file| {
                    file.read_to_end(&mut bytes)
                        .map_err(|e| format!("Unable to read {:?}: {:?}", file, e))
                })?;

            info!(
                genesis_file = ?genesis_file_path,
                bytes_len = bytes.len(),
                "Successfully loaded genesis state from file",
            );

            let state = Some(bytes).filter(|bytes| !bytes.is_empty());
            let genesis_state_source = if state.is_some() {
                GenesisStateSource::IncludedBytes
            } else {
                GenesisStateSource::Unknown
            };
            (state, genesis_state_source)
        } else {
            warn!(
                genesis_file = ?genesis_file_path,
                "Genesis state file not found, will use built-in or URL source",
            );
            (None, GenesisStateSource::Unknown)
        };

        let kzg_trusted_setup = get_trusted_setup();

        Ok(Self {
            deposit_contract_deploy_block,
            boot_enr,
            genesis_state_source,
            genesis_state_bytes: genesis_state_bytes.map(Into::into),
            config,
            kzg_trusted_setup,
        })
    }
}

/// Try to download a genesis state from each of the `urls` in the order they
/// are defined. Return `Ok` if any url returns a response that matches the
/// given `checksum`.
async fn download_genesis_state(
    urls: &[&str],
    timeout: Duration,
    checksum: Hash256,
) -> Result<Vec<u8>, String> {
    if urls.is_empty() {
        return Err(
            "The genesis state is not present in the binary and there are no known download URLs. \
            Please use --checkpoint-sync-url or --genesis-state-url."
                .to_string(),
        );
    }

    let mut errors = vec![];
    for url in urls {
        // URLs are always expected to be the base URL of a server that supports
        // the beacon-API.
        let url = parse_state_download_url(url)?;
        let redacted_url = SensitiveUrl::new(url.clone())
            .map(|url| url.to_string())
            .unwrap_or_else(|_| "<REDACTED>".to_string());

        info!(
            server = &redacted_url,
            timeout = ?timeout,
            info = "this may take some time on testnets with large validator counts",
            "Downloading genesis state"
        );

        let client = Client::new();
        let response = get_state_bytes(timeout, url, client).await;

        match response {
            Ok(bytes) => {
                // Check the server response against our local checksum.
                if Sha256::digest(bytes.as_ref())[..] == checksum[..] {
                    return Ok(bytes.into());
                } else {
                    warn!(
                        server = &redacted_url,
                        timeout = ?timeout,
                        "Genesis state download failed"
                    );
                    errors.push(format!(
                        "Response from {} did not match local checksum",
                        redacted_url
                    ))
                }
            }
            Err(e) => errors.push(PrettyReqwestError::from(e).to_string()),
        }
    }
    Err(format!(
        "Unable to download a genesis state from {} source(s): {}",
        errors.len(),
        errors.join(",")
    ))
}

async fn get_state_bytes(timeout: Duration, url: Url, client: Client) -> Result<Bytes, Error> {
    client
        .get(url)
        .header("Accept", "application/octet-stream")
        .timeout(timeout)
        .send()
        .await?
        .error_for_status()?
        .bytes()
        .await
}

/// Parses the `url` and joins the necessary state download path.
fn parse_state_download_url(url: &str) -> Result<Url, String> {
    Url::parse(url)
        .map_err(|e| format!("Invalid genesis state URL: {:?}", e))?
        .join("eth/v2/debug/beacon/states/genesis")
        .map_err(|e| format!("Failed to append genesis state path to URL: {:?}", e))
}

#[cfg(test)]
mod tests {
    use super::*;
    use ssz::Encode;
    use tempfile::Builder as TempBuilder;
    use types::{Eth1Data, FixedBytesExtended, GnosisEthSpec, MainnetEthSpec};

    type E = MainnetEthSpec;

    #[test]
    fn default_network_exists() {
        assert!(HARDCODED_NET_NAMES.contains(&DEFAULT_HARDCODED_NETWORK));
    }

    #[test]
    fn hardcoded_testnet_names() {
        assert_eq!(HARDCODED_NET_NAMES.len(), HARDCODED_NETS.len());
        for (name, net) in HARDCODED_NET_NAMES.iter().zip(HARDCODED_NETS.iter()) {
            assert_eq!(name, &net.name);
        }
    }

    #[test]
    fn mainnet_config_eq_chain_spec() {
        let config = Eth2NetworkConfig::from_hardcoded_net(&MAINNET).unwrap();
        let spec = ChainSpec::mainnet();
        assert_eq!(spec, config.chain_spec::<E>().unwrap());
    }

    #[test]
    fn gnosis_config_eq_chain_spec() {
        let config = Eth2NetworkConfig::from_hardcoded_net(&GNOSIS).unwrap();
        let spec = ChainSpec::gnosis();
        assert_eq!(spec, config.chain_spec::<GnosisEthSpec>().unwrap());
    }

    #[tokio::test]
    async fn mainnet_genesis_state() {
        let config = Eth2NetworkConfig::from_hardcoded_net(&MAINNET).unwrap();
        config
            .genesis_state::<E>(None, Duration::from_secs(1))
            .expect("beacon state can decode");
    }

    #[test]
    fn hard_coded_nets_work() {
        for net in HARDCODED_NETS {
            let config = Eth2NetworkConfig::from_hardcoded_net(net)
                .unwrap_or_else(|e| panic!("{:?}: {:?}", net.name, e));

            // Ensure we can parse the YAML config to a chain spec.
            if config.config.preset_base == types::GNOSIS {
                config.chain_spec::<GnosisEthSpec>().unwrap();
            } else {
                config.chain_spec::<MainnetEthSpec>().unwrap();
            }

            assert_eq!(
                config.genesis_state_bytes.is_some(),
                net.genesis_state_source == GenesisStateSource::IncludedBytes,
                "{:?}",
                net.name
            );

            if let GenesisStateSource::Url {
                urls,
                checksum,
                genesis_validators_root,
                ..
            } = net.genesis_state_source
            {
                Hash256::from_str(checksum).expect("the checksum must be a valid 32-byte value");
                Hash256::from_str(genesis_validators_root)
                    .expect("the GVR must be a valid 32-byte value");
                for url in urls {
                    parse_state_download_url(url).expect("url must be valid");
                }
            }

            assert_eq!(config.config.config_name, Some(net.config_dir.to_string()));
        }
    }

    #[test]
    fn round_trip() {
        let spec = &E::default_spec();

        let eth1_data = Eth1Data {
            deposit_root: Hash256::zero(),
            deposit_count: 0,
            block_hash: Hash256::zero(),
        };

        // TODO: figure out how to generate ENR and add some here.
        let boot_enr = None;
        let genesis_state = Some(BeaconState::new(42, eth1_data, spec));
        let config = Config::from_chain_spec::<E>(spec);

        do_test::<E>(boot_enr, genesis_state, config.clone());
        do_test::<E>(None, None, config);
    }

    fn do_test<E: EthSpec>(
        boot_enr: Option<Vec<Enr<CombinedKey>>>,
        genesis_state: Option<BeaconState<E>>,
        config: Config,
    ) {
        let temp_dir = TempBuilder::new()
            .prefix("eth2_testnet_test")
            .tempdir()
            .expect("should create temp dir");
        let base_dir = temp_dir.path().join("my_testnet");
        let deposit_contract_deploy_block = 42;

        let genesis_state_source = if genesis_state.is_some() {
            GenesisStateSource::IncludedBytes
        } else {
            GenesisStateSource::Unknown
        };
        // With Deneb enabled by default we must set a trusted setup here.
        let kzg_trusted_setup = get_trusted_setup();

        let testnet = Eth2NetworkConfig {
            deposit_contract_deploy_block,
            boot_enr,
            genesis_state_source,
            genesis_state_bytes: genesis_state
                .as_ref()
                .map(Encode::as_ssz_bytes)
                .map(Into::into),
            config,
            kzg_trusted_setup,
        };

        testnet
            .write_to_file(base_dir.clone(), false)
            .expect("should write to file");

        let decoded = Eth2NetworkConfig::load(base_dir).expect("should load struct");

        assert_eq!(testnet, decoded, "should decode as encoded");
    }
}
