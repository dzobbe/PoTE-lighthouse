use crate::tee_attestation::{TEEQuote, TEE_QUOTE_SIZE};
use crate::tee_types::TEEType;
use crate::test_utils::TestRandom;
use crate::*;

use context_deserialize::context_deserialize;
use serde::{Deserialize, Serialize};
use ssz::DecodeError;
use ssz_derive::Encode;
use ssz_types::VariableList;
use test_random_derive::TestRandom;
use typenum::U131072;
use tree_hash::TreeHash;
use tree_hash_derive::TreeHash;

/// A header of a `BeaconBlock`.
///
/// Spec v0.12.1
/// Extended with TEE (Trusted Execution Environment) information for multi-vendor TEE consensus
#[cfg_attr(feature = "arbitrary", derive(arbitrary::Arbitrary))]
#[derive(
    Debug, PartialEq, Eq, Hash, Clone, Serialize, Deserialize, Encode, TreeHash, TestRandom,
)]
#[context_deserialize(ForkName)]
pub struct BeaconBlockHeader {
    pub slot: Slot,
    #[serde(with = "serde_utils::quoted_u64")]
    pub proposer_index: u64,
    pub parent_root: Hash256,
    pub state_root: Hash256,
    pub body_root: Hash256,
    /// TEE type of the validator proposing this block (SEV, TDX, or CCA)
    pub proposer_tee_type: TEEType,
    /// Fixed-size attestation quote provided by the proposer (8 KiB base64 payload).
    pub proposer_tee_quote: TEEQuote,
}

impl SignedRoot for BeaconBlockHeader {}

impl BeaconBlockHeader {
    /// Returns the `tree_hash_root` of the header.
    ///
    /// Spec v0.12.1
    pub fn canonical_root(&self) -> Hash256 {
        Hash256::from_slice(&self.tree_hash_root()[..])
    }

    /// Signs `self`, producing a `SignedBeaconBlockHeader`.
    pub fn sign<E: EthSpec>(
        self,
        secret_key: &SecretKey,
        fork: &Fork,
        genesis_validators_root: Hash256,
        spec: &ChainSpec,
    ) -> SignedBeaconBlockHeader {
        let epoch = self.slot.epoch(E::slots_per_epoch());
        let domain = spec.get_domain(epoch, Domain::BeaconProposer, fork, genesis_validators_root);
        let message = self.signing_root(domain);
        let signature = secret_key.sign(message);
        SignedBeaconBlockHeader {
            message: self,
            signature,
        }
    }

    pub fn empty() -> Self {
        Self {
            body_root: Default::default(),
            parent_root: Default::default(),
            proposer_index: Default::default(),
            slot: Default::default(),
            state_root: Default::default(),
            proposer_tee_type: TEEType::SEV,
            proposer_tee_quote: TEEQuote::default(),
        }
    }

    /// Creates a placeholder quote for block production.
    /// In production, this should be replaced with real attestation generation.
    pub fn create_placeholder_tee_quote() -> TEEQuote {
        TEEQuote::from_bytes([0xAA; TEE_QUOTE_SIZE])
    }

    /// Gets a placeholder TEE type for testing/development
    /// In production, this should be determined from the validator's actual TEE
    pub fn placeholder_tee_type() -> TEEType {
        // TODO: Rotate between different TEE types for testing
        TEEType::TDX
    }
}

#[derive(ssz_derive::Decode)]
struct BeaconBlockHeaderSsz {
    slot: Slot,
    proposer_index: u64,
    parent_root: Hash256,
    state_root: Hash256,
    body_root: Hash256,
    proposer_tee_type: TEEType,
    proposer_tee_quote: TEEQuote,
}

#[derive(ssz_derive::Decode)]
struct BeaconBlockHeaderVariable {
    slot: Slot,
    proposer_index: u64,
    parent_root: Hash256,
    state_root: Hash256,
    body_root: Hash256,
    proposer_tee_type: TEEType,
    proposer_tee_quote: VariableList<u8, U131072>,
}

impl From<BeaconBlockHeaderSsz> for BeaconBlockHeader {
    fn from(value: BeaconBlockHeaderSsz) -> Self {
        Self {
            slot: value.slot,
            proposer_index: value.proposer_index,
            parent_root: value.parent_root,
            state_root: value.state_root,
            body_root: value.body_root,
            proposer_tee_type: value.proposer_tee_type,
            proposer_tee_quote: value.proposer_tee_quote,
        }
    }
}

impl From<BeaconBlockHeaderVariable> for BeaconBlockHeader {
    fn from(value: BeaconBlockHeaderVariable) -> Self {
        let quote_bytes = if value.proposer_tee_quote.is_empty() {
            TEEQuote::default()
        } else {
            let slice: &[u8] = value.proposer_tee_quote.as_ref();
            tracing::info!(
                actual_len = slice.len(),
                expected_len = TEE_QUOTE_SIZE,
                "Decoding variable-length proposer TEE quote"
            );
            if slice.len() != TEE_QUOTE_SIZE {
                tracing::warn!(
                    actual_len = slice.len(),
                    expected_len = TEE_QUOTE_SIZE,
                    "TEE quote length differs from expected; padding or truncating as required"
                );
            }
            let mut array = [0u8; TEE_QUOTE_SIZE];
            let copy_len = slice.len().min(TEE_QUOTE_SIZE);
            array[..copy_len].copy_from_slice(&slice[..copy_len]);
            TEEQuote::from_bytes(array)
        };

        BeaconBlockHeader {
            slot: value.slot,
            proposer_index: value.proposer_index,
            parent_root: value.parent_root,
            state_root: value.state_root,
            body_root: value.body_root,
            proposer_tee_type: value.proposer_tee_type,
            proposer_tee_quote: quote_bytes,
        }
    }
}

const EXTENDED_HEADER_BYTES: usize = 8 + 8 + 32 * 3 + 1 + TEE_QUOTE_SIZE;

impl ssz::Decode for BeaconBlockHeader {
    fn is_ssz_fixed_len() -> bool {
        true
    }

    fn ssz_fixed_len() -> usize {
        EXTENDED_HEADER_BYTES
    }

    fn from_ssz_bytes(bytes: &[u8]) -> Result<Self, DecodeError> {
        const LEGACY_LEN: usize = 112;
        const EXPECTED_TEE_HEADER_LEN: usize = EXTENDED_HEADER_BYTES;

        tracing::info!(
            bytes_len = bytes.len(),
            expected_fixed_len = EXPECTED_TEE_HEADER_LEN,
            expected_legacy_len = LEGACY_LEN,
            "Decoding BeaconBlockHeader from SSZ bytes",
        );

        match BeaconBlockHeaderSsz::from_ssz_bytes(bytes) {
            Ok(header) => {
                let decoded: BeaconBlockHeader = header.into();
                use ssz::Encode;
                let encoded_size = decoded.as_ssz_bytes().len();
                tracing::info!(
                    decoded_size = encoded_size,
                    slot = decoded.slot.as_u64(),
                    proposer_index = decoded.proposer_index,
                    tee_type = ?decoded.proposer_tee_type,
                    "Successfully decoded BeaconBlockHeader (fixed-length TEE format)",
                );
                Ok(decoded)
            }
            Err(err) => {
                tracing::info!(
                    error = ?err,
                    bytes_len = bytes.len(),
                    "Initial decode attempt failed, trying fallback strategies",
                );
                
                if matches!(err, DecodeError::OffsetIntoFixedPortion(_)) {
                    tracing::info!(
                        "OffsetIntoFixedPortion error detected, attempting variable-length TEE quote decoding",
                    );
                    match BeaconBlockHeaderVariable::from_ssz_bytes(bytes) {
                        Ok(variable_header) => {
                            let decoded: BeaconBlockHeader = variable_header.into();
                            use ssz::Encode;
                            let encoded_size = decoded.as_ssz_bytes().len();
                            tracing::info!(
                                decoded_size = encoded_size,
                                slot = decoded.slot.as_u64(),
                                "Successfully decoded BeaconBlockHeader (variable-length TEE format)",
                            );
                            return Ok(decoded);
                        }
                        Err(variable_err) => {
                            tracing::error!(
                                original_error = ?err,
                                variable_error = ?variable_err,
                                total_bytes = bytes.len(),
                                expected_fixed_len = EXPECTED_TEE_HEADER_LEN,
                                "Failed to decode beacon block header with both fixed and variable-length TEE quote formats"
                            );
                        }
                    }
                }
                if bytes.len() == LEGACY_LEN {
                    tracing::info!(
                        bytes_len = bytes.len(),
                        "Attempting to decode legacy beacon block header (112 bytes, no TEE fields)",
                    );
                    match decode_legacy_header(bytes) {
                        Ok(legacy_header) => {
                            tracing::info!(
                                slot = legacy_header.slot.as_u64(),
                                "Successfully decoded legacy beacon block header",
                            );
                            return Ok(legacy_header);
                        }
                        Err(legacy_err) => {
                            tracing::error!(
                                legacy_error = ?legacy_err,
                                "Failed to decode legacy beacon block header",
                            );
                            return Err(err);
                        }
                    }
                }
                
                tracing::error!(
                    error = ?err,
                    bytes_len = bytes.len(),
                    expected_fixed_len = EXPECTED_TEE_HEADER_LEN,
                    expected_legacy_len = LEGACY_LEN,
                    "All decode attempts failed for BeaconBlockHeader",
                );
                Err(err)
            }
        }
    }
}

fn decode_legacy_header(bytes: &[u8]) -> Result<BeaconBlockHeader, DecodeError> {
    use std::convert::TryInto;

    const LEGACY_LEN: usize = 112;
    if bytes.len() != LEGACY_LEN {
        return Err(DecodeError::InvalidByteLength {
            len: bytes.len(),
            expected: LEGACY_LEN,
        });
    }

    let slot_bytes: [u8; 8] = bytes[0..8]
        .try_into()
        .map_err(|_| DecodeError::BytesInvalid("invalid slot length".into()))?;
    let proposer_index_bytes: [u8; 8] = bytes[8..16]
        .try_into()
        .map_err(|_| DecodeError::BytesInvalid("invalid proposer_index length".into()))?;

    let slot = Slot::new(u64::from_le_bytes(slot_bytes));
    let proposer_index = u64::from_le_bytes(proposer_index_bytes);
    let parent_root = Hash256::from(
        <[u8; 32]>::try_from(&bytes[16..48])
            .map_err(|_| DecodeError::BytesInvalid("invalid parent_root length".into()))?,
    );
    let state_root = Hash256::from(
        <[u8; 32]>::try_from(&bytes[48..80])
            .map_err(|_| DecodeError::BytesInvalid("invalid state_root length".into()))?,
    );
    let body_root = Hash256::from(
        <[u8; 32]>::try_from(&bytes[80..112])
            .map_err(|_| DecodeError::BytesInvalid("invalid body_root length".into()))?,
    );

    Ok(BeaconBlockHeader {
        slot,
        proposer_index,
        parent_root,
        state_root,
        body_root,
        proposer_tee_type: TEEType::SEV,
        proposer_tee_quote: TEEQuote::default(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    ssz_and_tree_hash_tests!(BeaconBlockHeader);
}
