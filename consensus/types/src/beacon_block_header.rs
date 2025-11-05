use crate::test_utils::TestRandom;
use crate::*;
use crate::tee_types::TEEType;
use crate::tee_attestation::TEEAttestation;

use context_deserialize::context_deserialize;
use serde::{Deserialize, Serialize};
use ssz_derive::{Decode, Encode};
use test_random_derive::TestRandom;
use tree_hash::TreeHash;
use tree_hash_derive::TreeHash;

/// A header of a `BeaconBlock`.
///
/// Spec v0.12.1
/// Extended with TEE (Trusted Execution Environment) information for multi-vendor TEE consensus
#[cfg_attr(feature = "arbitrary", derive(arbitrary::Arbitrary))]
#[derive(
    Debug, PartialEq, Eq, Hash, Clone, Serialize, Deserialize, Encode, Decode, TreeHash, TestRandom,
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
    /// TEE attestation quote from the proposer's TEE
    pub proposer_tee_attestation: TEEAttestation,
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
        use crate::tee_attestation::TEEQuote;
        
        // Create a placeholder TEE attestation for empty header
        let placeholder_quote = TEEQuote {
            quote_data: vec![0u8; 432], // Standard TEE quote size
            version: 3,
        };
        
        Self {
            body_root: Default::default(),
            parent_root: Default::default(),
            proposer_index: Default::default(),
            slot: Default::default(),
            state_root: Default::default(),
            proposer_tee_type: TEEType::SEV, // Default to SEV
            proposer_tee_attestation: TEEAttestation::new(placeholder_quote, u64::MAX),
        }
    }
    
    /// Creates a placeholder TEE attestation for block production
    /// In production, this should be replaced with actual TEE attestation generation
    pub fn create_placeholder_tee_attestation() -> TEEAttestation {
        use crate::tee_attestation::TEEQuote;
        
        // TODO: Replace with actual TEE attestation generation
        let placeholder_quote = TEEQuote {
            quote_data: vec![0xAA; 432], // Placeholder data
            version: 3,
        };
        
        TEEAttestation::new(placeholder_quote, u64::MAX)
    }
    
    /// Gets a placeholder TEE type for testing/development
    /// In production, this should be determined from the validator's actual TEE
    pub fn placeholder_tee_type() -> TEEType {
        // TODO: Rotate between different TEE types for testing
        TEEType::TDX
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    ssz_and_tree_hash_tests!(BeaconBlockHeader);
}
