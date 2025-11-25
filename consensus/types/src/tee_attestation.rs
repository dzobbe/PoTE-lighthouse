use crate::test_utils::TestRandom;
use serde::de::{Error as DeError, SeqAccess, Visitor};
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use ssz::{Decode, DecodeError, Encode};
use std::fmt;
use std::hash::{Hash, Hasher};
use tree_hash_derive::TreeHash;

/// Fixed size in bytes for an attestation quote included in a block header.
pub const TEE_QUOTE_SIZE: usize = 8192;

/// Raw quote bytes extracted from the proposer's attestation.
#[derive(Debug, Clone, PartialEq, Eq, TreeHash)]
pub struct TEEQuote {
    /// The raw quote bytes in binary form. Length is always `TEE_QUOTE_SIZE`.
    pub bytes: [u8; TEE_QUOTE_SIZE],
}

impl Default for TEEQuote {
    fn default() -> Self {
        Self {
            bytes: [0u8; TEE_QUOTE_SIZE],
        }
    }
}

impl Hash for TEEQuote {
    fn hash<H: Hasher>(&self, state: &mut H) {
        self.bytes.hash(state);
    }
}

impl Serialize for TEEQuote {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_bytes(&self.bytes)
    }
}

impl<'de> Deserialize<'de> for TEEQuote {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        struct QuoteVisitor;

        impl<'de> Visitor<'de> for QuoteVisitor {
            type Value = TEEQuote;

            fn expecting(&self, formatter: &mut fmt::Formatter) -> fmt::Result {
                write!(
                    formatter,
                    "a {}-byte attestation quote or base64 string",
                    TEE_QUOTE_SIZE
                )
            }

            fn visit_bytes<E>(self, v: &[u8]) -> Result<Self::Value, E>
            where
                E: DeError,
            {
                if v.len() != TEE_QUOTE_SIZE {
                    return Err(E::invalid_length(v.len(), &self));
                }
                let mut bytes = [0u8; TEE_QUOTE_SIZE];
                bytes.copy_from_slice(v);
                Ok(TEEQuote { bytes })
            }

            fn visit_seq<A>(self, mut seq: A) -> Result<Self::Value, A::Error>
            where
                A: SeqAccess<'de>,
            {
                let mut bytes = [0u8; TEE_QUOTE_SIZE];
                for idx in 0..TEE_QUOTE_SIZE {
                    let value: Option<u8> = seq.next_element()?;
                    let value = value.ok_or_else(|| DeError::invalid_length(idx, &self))?;
                    bytes[idx] = value;
                }
                if seq.next_element::<u8>()?.is_some() {
                    return Err(DeError::invalid_length(TEE_QUOTE_SIZE + 1, &self));
                }
                Ok(TEEQuote { bytes })
            }

            fn visit_str<E>(self, v: &str) -> Result<Self::Value, E>
            where
                E: DeError,
            {
                let decoded =
                    base64::decode(v).map_err(|e| DeError::custom(format!("base64 error: {e}")))?;
                self.visit_bytes(&decoded)
            }
        }

        deserializer.deserialize_bytes(QuoteVisitor)
    }
}

impl Encode for TEEQuote {
    fn is_ssz_fixed_len() -> bool {
        true
    }

    fn ssz_fixed_len() -> usize {
        TEE_QUOTE_SIZE
    }

    fn ssz_bytes_len(&self) -> usize {
        TEE_QUOTE_SIZE
    }

    fn ssz_append(&self, buf: &mut Vec<u8>) {
        buf.extend_from_slice(&self.bytes);
    }
}

impl Decode for TEEQuote {
    fn is_ssz_fixed_len() -> bool {
        true
    }

    fn ssz_fixed_len() -> usize {
        TEE_QUOTE_SIZE
    }

    fn from_ssz_bytes(bytes: &[u8]) -> Result<Self, DecodeError> {
        if bytes.is_empty() {
            // Allow empty payloads for backwards compatibility with legacy genesis artifacts.
            tracing::warn!(
                "TEE quote SSZ payload is empty; defaulting to zeroed attestation bytes"
            );
            return Ok(TEEQuote::default());
        }
        if bytes.len() != TEE_QUOTE_SIZE {
            return Err(DecodeError::InvalidByteLength {
                len: bytes.len(),
                expected: TEE_QUOTE_SIZE,
            });
        }
        let mut array = [0u8; TEE_QUOTE_SIZE];
        array.copy_from_slice(bytes);
        Ok(TEEQuote { bytes: array })
    }
}

impl TEEQuote {
    /// Construct a quote from raw bytes. Length must be exactly `TEE_QUOTE_SIZE`.
    pub fn from_bytes(bytes: [u8; TEE_QUOTE_SIZE]) -> Self {
        Self { bytes }
    }

    /// Decode a base64-encoded representation of the quote.
    /// If the decoded quote is smaller than TEE_QUOTE_SIZE, pads with zeros.
    pub fn from_base64(encoded: &str) -> Result<Self, TEEQuoteError> {
        let decoded = base64::decode(encoded).map_err(TEEQuoteError::Base64Decoding)?;
        if decoded.len() > TEE_QUOTE_SIZE {
            return Err(TEEQuoteError::InvalidLength {
                expected: TEE_QUOTE_SIZE,
                actual: decoded.len(),
            });
        }
        let mut bytes = [0u8; TEE_QUOTE_SIZE];
        let copy_len = decoded.len().min(TEE_QUOTE_SIZE);
        bytes[..copy_len].copy_from_slice(&decoded[..copy_len]);
        Ok(Self { bytes })
    }

    /// Create a quote from raw bytes, padding with zeros if smaller than TEE_QUOTE_SIZE.
    pub fn from_bytes_padded(data: &[u8]) -> Self {
        let mut bytes = [0u8; TEE_QUOTE_SIZE];
        let copy_len = data.len().min(TEE_QUOTE_SIZE);
        bytes[..copy_len].copy_from_slice(&data[..copy_len]);
        Self { bytes }
    }

    /// Encode the quote to a base64 string.
    pub fn to_base64(&self) -> String {
        base64::encode(self.bytes)
    }

    /// Returns a reference to the raw bytes.
    pub fn as_bytes(&self) -> &[u8; TEE_QUOTE_SIZE] {
        &self.bytes
    }
}

impl TestRandom for TEEQuote {
    fn random_for_test(rng: &mut impl rand::RngCore) -> Self {
        let mut bytes = [0u8; TEE_QUOTE_SIZE];
        rng.fill_bytes(&mut bytes);
        Self { bytes }
    }
}

/// Simple attestation verification result structure, retained for mock verification flows.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AttestationResult {
    /// Whether the the attestation is considered valid.
    pub is_valid: bool,
    /// Optional mock MRENCLAVE (measurement of the enclave).
    pub mrenclave: Option<[u8; 32]>,
    /// Optional mock MRSIGNER (measurement of the signer).
    pub mrsigner: Option<[u8; 32]>,
    /// Optional error message if verification failed.
    pub error_message: Option<String>,
}

/// Errors that can occur while working with fixed-size TEE quotes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TEEQuoteError {
    /// Base64 decoding failed.
    Base64Decoding(base64::DecodeError),
    /// Decoded data does not match the required length.
    InvalidLength { expected: usize, actual: usize },
}

impl fmt::Display for TEEQuoteError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            TEEQuoteError::Base64Decoding(err) => write!(f, "failed to decode base64 quote: {err}"),
            TEEQuoteError::InvalidLength { expected, actual } => {
                write!(f, "invalid quote length: expected {expected}, got {actual}")
            }
        }
    }
}

impl std::error::Error for TEEQuoteError {}
