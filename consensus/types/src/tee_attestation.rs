use serde::{Deserialize, Serialize};
use ssz_derive::{Decode, Encode};

/// SGX Quote structure for remote attestation
/// This represents the evidence provided by an SGX enclave
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Encode, Decode)]
pub struct SGXQuote {
    /// The SGX quote data (typically 432 bytes)
    pub quote_data: Vec<u8>,
    /// The version of the SGX quote
    pub version: u16,
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
    /// The SGX quote providing evidence of TEE
    pub sgx_quote: SGXQuote,
    /// Timestamp of when attestation was created
    pub created_at: u64,
    /// Timestamp of when attestation expires
    pub expires_at: u64,
    /// Optional signature over the quote
    pub signature: Option<Vec<u8>>,
}

impl TEEAttestation {
    /// Create a new TEE attestation
    pub fn new(sgx_quote: SGXQuote, expires_at: u64) -> Self {
        Self {
            sgx_quote,
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
