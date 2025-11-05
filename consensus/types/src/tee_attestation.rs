use serde::{Deserialize, Serialize};
use ssz_derive::{Decode, Encode};
use crate::test_utils::TestRandom;
use std::hash::{Hash, Hasher};
use tree_hash::TreeHash;

/// Generic TEE Quote structure for remote attestation
/// This represents the evidence provided by any TEE (SEV, TDX, CCA, etc.)
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Encode, Decode)]
pub struct TEEQuote {
    /// The TEE quote data (size varies by TEE type: typically 432 bytes for SGX-like attestations)
    pub quote_data: Vec<u8>,
    /// The version of the attestation format
    pub version: u16,
}

impl Hash for TEEQuote {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.quote_data.hash(state);
        self.version.hash(state);
    }
}

impl TreeHash for TEEQuote {
    fn tree_hash_type() -> tree_hash::TreeHashType {
        tree_hash::TreeHashType::List
    }

    fn tree_hash_packed_encoding(&self) -> smallvec::SmallVec<[u8; 32]> {
        unreachable!("List should never be packed.")
    }

    fn tree_hash_packing_factor() -> usize {
        unreachable!("List should never be packed.")
    }

    fn tree_hash_root(&self) -> tree_hash::Hash256 {
        // Hash the quote_data and version together
        let mut bytes = self.quote_data.clone();
        bytes.extend_from_slice(&self.version.to_le_bytes());
        tree_hash::Hash256::from_slice(&ethereum_hashing::hash(&bytes))
    }
}

impl TestRandom for TEEQuote {
    fn random_for_test(rng: &mut impl rand::RngCore) -> Self {
        let mut quote_data = vec![0u8; 432];
        rng.fill_bytes(&mut quote_data);
        Self {
            quote_data,
            version: (rng.next_u32() % 10) as u16,
        }
    }
}

/// Attestation verification result
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttestationResult {
    /// Whether the attestation is valid
    pub is_valid: bool,
    /// Optional MRENCLAVE (measurement of the enclave)
    pub mrenclave: Option<[u8; 32]>,
    /// Optional MRSIGNER (measurement of the signer)
    pub mrsigner: Option<[u8; 32]>,
    /// Error message if verification failed
    pub error_message: Option<String>,
}

/// Represents a validator's TEE attestation status
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Encode, Decode)]
pub struct TEEAttestation {
    /// The TEE quote providing evidence of trusted execution environment
    pub tee_quote: TEEQuote,
    /// Timestamp of when attestation was created
    pub created_at: u64,
    /// Timestamp of when attestation expires
    pub expires_at: u64,
    /// Optional signature over the quote
    pub signature: Option<Vec<u8>>,
}

impl Hash for TEEAttestation {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.tee_quote.hash(state);
        self.created_at.hash(state);
        self.expires_at.hash(state);
        self.signature.hash(state);
    }
}

impl TreeHash for TEEAttestation {
    fn tree_hash_type() -> tree_hash::TreeHashType {
        tree_hash::TreeHashType::Container
    }

    fn tree_hash_packed_encoding(&self) -> smallvec::SmallVec<[u8; 32]> {
        unreachable!("Container should never be packed.")
    }

    fn tree_hash_packing_factor() -> usize {
        unreachable!("Container should never be packed.")
    }

    fn tree_hash_root(&self) -> tree_hash::Hash256 {
        // Combine all fields for hashing
        let quote_hash = self.tee_quote.tree_hash_root();
        let mut bytes = Vec::new();
        bytes.extend_from_slice(&quote_hash[..]);
        bytes.extend_from_slice(&self.created_at.to_le_bytes());
        bytes.extend_from_slice(&self.expires_at.to_le_bytes());
        if let Some(sig) = &self.signature {
            bytes.extend_from_slice(sig);
        }
        tree_hash::Hash256::from_slice(&ethereum_hashing::hash(&bytes))
    }
}

impl TestRandom for TEEAttestation {
    fn random_for_test(rng: &mut impl rand::RngCore) -> Self {
        Self {
            tee_quote: TEEQuote::random_for_test(rng),
            created_at: rng.next_u64(),
            expires_at: rng.next_u64(),
            signature: if rng.next_u32() % 2 == 0 {
                let mut sig = vec![0u8; 64];
                rng.fill_bytes(&mut sig);
                Some(sig)
            } else {
                None
            },
        }
    }
}

impl TEEAttestation {
    /// Create a new TEE attestation
    pub fn new(tee_quote: TEEQuote, expires_at: u64) -> Self {
        Self {
            tee_quote,
            created_at: 0, // Will be set by the system
            expires_at,
            signature: None,
        }
    }

    /// Check if the attestation is currently valid (not expired)
    pub fn is_not_expired(&self, current_time: u64) -> bool {
        current_time < self.expires_at
    }
}
