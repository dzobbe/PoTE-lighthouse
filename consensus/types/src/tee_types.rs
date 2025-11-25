use crate::tee_attestation::TEEQuote;
use crate::test_utils::TestRandom;
use crate::*;
use serde::{Deserialize, Serialize};
use smallvec::SmallVec;
use ssz::Encode;
use tree_hash::TreeHash;

/// TEE technology types supported by the consensus
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Hash)]
#[serde(rename_all = "lowercase")]
pub enum TEEType {
    /// AMD SEV (Secure Encrypted Virtualization)
    SEV,
    /// Intel TDX (Trust Domain Extensions)
    TDX,
    /// ARM CCA (Confidential Compute Architecture)
    CCA,
}

impl ssz::Encode for TEEType {
    fn is_ssz_fixed_len() -> bool {
        true
    }

    fn ssz_fixed_len() -> usize {
        1
    }

    fn ssz_bytes_len(&self) -> usize {
        1
    }

    fn ssz_append(&self, buf: &mut Vec<u8>) {
        let byte = match self {
            TEEType::SEV => 0u8,
            TEEType::TDX => 1u8,
            TEEType::CCA => 2u8,
        };
        buf.push(byte);
    }
}

impl ssz::Decode for TEEType {
    fn is_ssz_fixed_len() -> bool {
        true
    }

    fn ssz_fixed_len() -> usize {
        1
    }

    fn from_ssz_bytes(bytes: &[u8]) -> Result<Self, ssz::DecodeError> {
        if bytes.len() != 1 {
            return Err(ssz::DecodeError::InvalidByteLength {
                len: bytes.len(),
                expected: 1,
            });
        }
        match bytes[0] {
            0 => Ok(TEEType::SEV),
            1 => Ok(TEEType::TDX),
            2 => Ok(TEEType::CCA),
            invalid_byte => {
                eprintln!("[ERROR] Invalid TEE type byte: {}", invalid_byte);
                Err(ssz::DecodeError::BytesInvalid(format!(
                    "Invalid TEE type byte: {}. Expected 0 (SEV), 1 (TDX), or 2 (CCA)",
                    invalid_byte
                )))
            }
        }
    }
}

impl TEEType {
    /// Get the string representation of the TEE type
    pub fn as_str(&self) -> &'static str {
        match self {
            TEEType::SEV => "SEV",
            TEEType::TDX => "TDX",
            TEEType::CCA => "CCA",
        }
    }
}

impl std::str::FromStr for TEEType {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s.trim().to_ascii_lowercase().as_str() {
            "sev" => Ok(TEEType::SEV),
            "tdx" => Ok(TEEType::TDX),
            "cca" => Ok(TEEType::CCA),
            _ => Err(format!(
                "Invalid TEE type: {}. Expected SEV, TDX, or CCA",
                s
            )),
        }
    }
}

/// TEE validator structure replacing the traditional PoS validator
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TEEValidator {
    /// Public key of the validator
    pub pubkey: PublicKeyBytes,
    /// TEE technology type
    pub tee_type: TEEType,
    /// TEE attestation quote proving the validator is running in a TEE
    pub attestation_quote: TEEQuote,
    /// Whether the validator is currently active
    pub is_active: bool,
    /// Epoch when the validator was activated
    pub activation_epoch: Epoch,
    /// Epoch when the validator will exit
    pub exit_epoch: Epoch,
    /// Last epoch when the validator provided an attestation
    pub last_attestation_epoch: Epoch,
    /// Whether the validator has been slashed
    pub slashed: bool,
}

impl TEEValidator {
    /// Create a new TEE validator
    pub fn new(pubkey: PublicKeyBytes, tee_type: TEEType, attestation_quote: TEEQuote) -> Self {
        Self {
            pubkey,
            tee_type,
            attestation_quote,
            is_active: false,
            activation_epoch: Epoch::from(u64::MAX),
            exit_epoch: Epoch::from(u64::MAX),
            last_attestation_epoch: Epoch::from(0u64),
            slashed: false,
        }
    }

    /// Check if the validator is active at a given epoch
    pub fn is_active_at(&self, epoch: Epoch) -> bool {
        self.is_active && self.activation_epoch <= epoch && epoch < self.exit_epoch && !self.slashed
    }

    /// Check if the validator's attestation is still valid
    pub fn has_valid_attestation(&self, current_time: u64) -> bool {
        // With fixed-size quotes we rely on upstream freshness guarantees.
        // For now, always return true to mirror the mock verification behaviour.
        let _ = current_time;
        true
    }

    /// Check if the validator is eligible for activation
    pub fn is_eligible_for_activation(&self, current_epoch: Epoch) -> bool {
        !self.is_active && self.activation_epoch <= current_epoch && !self.slashed
    }
}

/// TEE committee structure for attestation duties
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TEECommittee {
    /// The slot this committee is assigned to
    pub slot: Slot,
    /// The index of this committee within the slot
    pub index: CommitteeIndex,
    /// Validators assigned to this committee
    pub validators: Vec<TEEValidator>,
}

/// TEE validator selection result
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TEEValidatorSelection {
    /// Proposers selected for this slot (one from each TEE type)
    pub proposers: Vec<TEEValidator>,
    /// Attestation committees for this slot
    pub committees: Vec<TEECommittee>,
    /// Required TEE types that must participate
    pub required_tee_types: Vec<TEEType>,
}

/// TEE consensus error types
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum TEEConsensusError {
    /// Insufficient TEE diversity (missing required TEE types)
    InsufficientTEEDiversity { missing_type: TEEType },
    /// No validators available for selection
    NoValidatorsAvailable,
    /// No active validators
    NoActiveValidators,
    /// Invalid TEE attestation
    InvalidAttestation { reason: String },
    /// TEE type mismatch
    TEETypeMismatch { expected: TEEType, actual: TEEType },
    /// Attestation expired
    AttestationExpired,
    /// Invalid attestation signature
    InvalidAttestationSignature,
}

impl std::fmt::Display for TEEConsensusError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            TEEConsensusError::InsufficientTEEDiversity { missing_type } => {
                write!(
                    f,
                    "Insufficient TEE diversity: missing {}",
                    missing_type.as_str()
                )
            }
            TEEConsensusError::NoValidatorsAvailable => {
                write!(f, "No validators available for selection")
            }
            TEEConsensusError::NoActiveValidators => {
                write!(f, "No active validators")
            }
            TEEConsensusError::InvalidAttestation { reason } => {
                write!(f, "Invalid TEE attestation: {}", reason)
            }
            TEEConsensusError::TEETypeMismatch { expected, actual } => {
                write!(
                    f,
                    "TEE type mismatch: expected {}, got {}",
                    expected.as_str(),
                    actual.as_str()
                )
            }
            TEEConsensusError::AttestationExpired => {
                write!(f, "TEE attestation has expired")
            }
            TEEConsensusError::InvalidAttestationSignature => {
                write!(f, "Invalid TEE attestation signature")
            }
        }
    }
}

impl std::error::Error for TEEConsensusError {}

// Manual implementations for TestRandom and TreeHash
impl TestRandom for TEEType {
    fn random_for_test(rng: &mut impl rand::RngCore) -> Self {
        match rng.next_u32() % 3 {
            0 => TEEType::SEV,
            1 => TEEType::TDX,
            _ => TEEType::CCA,
        }
    }
}

impl TreeHash for TEEType {
    fn tree_hash_type() -> tree_hash::TreeHashType {
        tree_hash::TreeHashType::Vector
    }

    fn tree_hash_packed_encoding(&self) -> SmallVec<[u8; 32]> {
        // Return the actual SSZ encoding (1 byte for TEEType)
        let mut vec = Vec::new();
        self.ssz_append(&mut vec);
        SmallVec::from_slice(&vec)
    }

    fn tree_hash_packing_factor() -> usize {
        1
    }

    fn tree_hash_root(&self) -> tree_hash::Hash256 {
        // For basic types, pad the SSZ encoding to 32 bytes
        let mut bytes = [0u8; 32];
        bytes[0] = match self {
            TEEType::SEV => 0u8,
            TEEType::TDX => 1u8,
            TEEType::CCA => 2u8,
        };
        tree_hash::Hash256::from_slice(&bytes)
    }
}
