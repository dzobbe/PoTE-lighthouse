# TEE (Trusted Execution Environment) Implementation for Lighthouse

## Overview

This implementation replaces Ethereum's **Proof-of-Stake (PoS)** staking requirements with **TEE attestation verification** using Intel SGX remote attestation. Validators must now provide verified SGX quotes instead of staking ETH.

## Architecture

### Key Components

#### 1. TEE Attestation Types (`consensus/types/src/tee_attestation.rs`)

- **`SGXQuote`**: Represents an SGX quote structure for remote attestation
- **`AttestationResult`**: Result of attestation verification with MRENCLAVE/MRSIGNER
- **`TEEAttestation`**: Complete attestation structure with expiration handling

#### 2. Attestation Service (`consensus/types/src/attestation_service.rs`)

- **`AzureAttestationService`**: Mock client for Azure Attestation Service integration
  - Production endpoint: `https://attest.azure.net`
  - Mock mode for testing
- **`AttestationCache`**: Cache for verification results

#### 3. Validator Changes (`consensus/types/src/validator.rs`)

- Added `tee_attestation: Option<TEEAttestation>` field to `Validator` struct
- Modified `is_eligible_for_activation_queue_*` to check TEE attestation instead of balance
- Added `has_verified_tee_attestation()` method

#### 4. Epoch Processing Changes

**Registry Updates** (`consensus/state_processing/src/per_epoch_processing/registry_updates.rs`):
- Modified ejection logic to eject validators without valid TEE attestation

**TEE Verification** (`consensus/state_processing/src/per_epoch_processing/tee_attestation_verification.rs`):
- New module for processing TEE attestation verification
- Placeholder for full async verification implementation

## Key Changes from Original PoS

### Before (Proof of Stake)
```rust
// Validator eligibility required:
effective_balance >= spec.max_effective_balance  // 32 ETH
```

### After (TEE Attestation)
```rust
// Validator eligibility now requires:
has_verified_tee_attestation()  // Valid SGX quote
```

## SGX Quote Structure

SGX quotes are typically 432 bytes and contain:
- Version information
- Quote signature
- Attestation key certificate
- Report with MRENCLAVE and MRSIGNER
- Report data

## Azure Attestation Service Integration

### Mock Implementation

The current implementation includes a mock Azure Attestation Service:

```rust
let attestation_service = AzureAttestationService::new_mock();
let result = attestation_service.verify_quote(&quote).await;
```

### Production Integration TODO

1. **HTTP Client Setup**: Use `reqwest` or similar for API calls
2. **Authentication**: Azure AD token authentication
3. **Quote Validation**: 
   - Send SGX quote to Azure endpoint
   - Verify certificate chain
   - Extract MRENCLAVE/MRSIGNER values
   - Validate against expected values
4. **Error Handling**: Proper error types and retry logic

### Example Production Code (Placeholder)

```rust
impl AzureAttestationService {
    pub async fn verify_quote_real(&self, quote: &SGXQuote) -> AttestationResult {
        let client = reqwest::Client::new();
        let url = format!("{}/attest/sgx?api-version=2022-08-01", self.endpoint);
        
        let response = client
            .post(&url)
            .header("Content-Type", "application/json")
            .json(&quote)
            .send()
            .await?;
            
        // Parse response and extract attestation result
        // ...
    }
}
```

## Validator Lifecycle

1. **Registration**: Validator submits deposit with SGX quote
2. **Attestation Verification**: System verifies quote via Azure Attestation Service
3. **Activation Queue**: Only validators with verified TEE attestations join queue
4. **Active Validation**: Validators participate in consensus
5. **Monitoring**: TEE attestations checked periodically for expiration
6. **Ejection**: Validators without valid/expired attestations are ejected

## Testing

### Mock Mode

Use mock attestation service for testing:

```rust
let service = AzureAttestationService::new_mock();
// All quotes will be accepted (for testing only)
```

### Test Scenarios

1. **Valid Attestation**: Validator with valid SGX quote activates successfully
2. **Expired Attestation**: Validator with expired attestation gets ejected
3. **Invalid Quote**: Validator with malformed quote cannot activate
4. **No Attestation**: Validator without TEE attestation cannot participate

## Security Considerations

### Current Implementation (Mock)

⚠️ **WARNING**: Current implementation uses mock verification for development only. 

### Production Requirements

1. **Real SGX Hardware**: Validators must run on SGX-enabled hardware
2. **Enclave Validation**: Enclaves must be cryptographically verified
3. **Quote Expiration**: Implement proper expiration checks
4. **Certificate Validation**: Verify Intel's certificate chain
5. **Rate Limiting**: Prevent attestation service abuse
6. **Caching**: Cache verified attestations to reduce API calls

## Migration Path

### Phase 1: Mock Implementation ✅
- Basic structure in place
- Mock verification service
- Validator struct updated

### Phase 2: Azure Integration
- Implement real HTTP client
- Add authentication
- Parse attestation responses

### Phase 3: Quote Parsing
- Parse SGX quote binary format
- Extract MRENCLAVE/MRSIGNER
- Validate certificate chain

### Phase 4: Production Deployment
- Deploy to testnet
- Monitor performance
- Security audit

## Dependencies to Add

For production implementation, add to `Cargo.toml`:

```toml
[dependencies]
reqwest = { version = "0.11", features = ["json"] }
async-trait = "0.1"
tokio = { version = "1", features = ["full"] }
azure_core = "0.18"
azure_identity = "0.14"
```

## References

- [Intel SGX Documentation](https://www.intel.com/content/www/us/en/developer/tools/software-guard-extensions/overview.html)
- [Azure Attestation Service](https://learn.microsoft.com/en-us/azure/attestation/overview)
- [Remote Attestation Concepts](https://www.intel.com/content/www/us/en/developer/tools/software-guard-extensions/attestation-guide.html)

## Next Steps

1. Implement real Azure Attestation Service HTTP client
2. Add proper SGX quote parsing
3. Implement certificate chain validation
4. Add comprehensive tests
5. Performance optimization and caching
6. Security audit before production deployment
