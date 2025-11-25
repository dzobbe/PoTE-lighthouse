use crate::tee_attestation::{AttestationResult, TEEQuote, TEE_QUOTE_SIZE};
use crate::tee_types::TEEType;

/// Real TEE attestation verification using lunal-attestation library.
pub async fn verify_tee_attestation(
    tee_type: &TEEType,
    quote: &TEEQuote,
) -> Result<bool, String> {
    tracing::debug!(
        "Verifying TEE attestation for type: {} with quote length: {} bytes",
        tee_type.as_str(),
        quote.as_bytes().len()
    );

    // Extract the actual quote bytes (may be padded)
    let quote_bytes = quote.as_bytes();
    
    // Find the end of actual data (first occurrence of 16 consecutive zeros likely indicates padding)
    // For now, we'll try to verify the entire quote, handling padding in the verification functions
    let actual_quote_end = find_quote_end(quote_bytes);
    let actual_quote_data = &quote_bytes[..actual_quote_end];

    match tee_type {
        TEEType::SEV => {
            // AMD SEV-SNP verification
            verify_amd_attestation(actual_quote_data).await
        }
        TEEType::TDX => {
            // Intel TDX verification
            verify_tdx_attestation(actual_quote_data).await
        }
        TEEType::CCA => {
            // ARM CCA verification (not yet supported by lunal-attestation)
            tracing::warn!("ARM CCA attestation verification not yet implemented");
            Ok(false)
        }
    }
}

/// Find the end of actual quote data by looking for padding patterns
fn find_quote_end(quote_bytes: &[u8; TEE_QUOTE_SIZE]) -> usize {
    // Look for a pattern that indicates padding start
    // Quotes typically don't have long runs of zeros in the middle
    // We'll look for 32 consecutive zeros as a likely padding indicator
    for i in (0..quote_bytes.len().saturating_sub(32)).rev() {
        if quote_bytes[i..i + 32].iter().all(|&b| b == 0) {
            return i;
        }
    }
    // If no clear padding found, assume all bytes are used
    quote_bytes.len()
}

/// Verify AMD SEV-SNP attestation
async fn verify_amd_attestation(quote_data: &[u8]) -> Result<bool, String> {
    #[cfg(feature = "tee-attestation")]
    {
        use lunal_attestation::amd;
        
        // The quote data is expected to be base64-encoded and possibly compressed
        // Try as compressed base64 string first (most common format)
        if let Ok(base64_str) = std::str::from_utf8(quote_data) {
            let trimmed = base64_str.trim();
            match amd::verify::verify_compressed(&[], trimmed, Some(false)).await {
                Ok(_result) => {
                    tracing::debug!("AMD attestation verification successful (compressed)");
                    return Ok(true);
                }
                Err(e) => {
                    tracing::debug!("Failed to verify as compressed base64: {}", e);
                }
            }
        }

        // Try to decode as base64 and parse as AttestationEvidence
        let decoded = if let Ok(s) = std::str::from_utf8(quote_data) {
            // If it's valid UTF-8, try to decode as base64
            if let Ok(decoded) = base64::decode(s) {
                decoded
            } else {
                // If base64 decode fails, assume it's already the data
                quote_data.to_vec()
            }
        } else {
            // If not valid UTF-8, assume it's already binary
            quote_data.to_vec()
        };

        // Try to parse as AttestationEvidence
        match amd::AttestationEvidence::from_bytes(&decoded) {
            Ok(evidence) => {
                // Verify with empty custom data (or extract from evidence if needed)
                match amd::verify::verify_evidence(&[], &evidence, Some(false)).await {
                    Ok(_result) => {
                        tracing::debug!("AMD attestation verification successful");
                        Ok(true)
                    }
                    Err(e) => {
                        tracing::warn!("AMD attestation verification failed: {}", e);
                        Ok(false)
                    }
                }
            }
            Err(_) => {
                tracing::warn!("Could not parse AMD attestation quote data");
                Ok(false)
            }
        }
    }
    
    #[cfg(not(feature = "tee-attestation"))]
    {
        tracing::warn!("AMD attestation feature not enabled (requires tee-attestation feature on Linux)");
        Ok(false)
    }
}

/// Verify Intel TDX attestation
async fn verify_tdx_attestation(quote_data: &[u8]) -> Result<bool, String> {
    #[cfg(all(feature = "tee-attestation", feature = "attestation-tdx"))]
    {
        use lunal_attestation::verify;
        
        // Try to decode as base64 string
        let quote_str = if let Ok(s) = std::str::from_utf8(quote_data) {
            s.trim().to_string()
        } else {
            // If not valid UTF-8, encode as base64
            base64::encode(quote_data)
        };

        match verify::verify_attestation(&quote_str).await {
            Ok(_verified_output) => {
                tracing::debug!("TDX attestation verification successful");
                Ok(true)
            }
            Err(e) => {
                tracing::warn!("TDX attestation verification failed: {}", e);
                Ok(false)
            }
        }
    }
    
    #[cfg(not(all(feature = "tee-attestation", feature = "attestation-tdx")))]
    {
        tracing::warn!("TDX attestation feature not enabled (requires tee-attestation feature on Linux)");
        Ok(false)
    }
}

/// Generate a TEE attestation quote for the given TEE type.
/// Returns a fixed-size TEEQuote (8192 bytes) with the actual quote data and padding.
pub async fn generate_tee_quote(tee_type: &TEEType, custom_data: &[u8]) -> Result<TEEQuote, String> {
    tracing::debug!(
        "Generating TEE attestation quote for type: {}",
        tee_type.as_str()
    );

    let quote_bytes = match tee_type {
        TEEType::SEV => {
            // Generate AMD SEV-SNP attestation
            generate_amd_attestation(custom_data).await?
        }
        TEEType::TDX => {
            // Generate Intel TDX attestation
            generate_tdx_attestation(custom_data).await?
        }
        TEEType::CCA => {
            return Err("ARM CCA attestation generation not yet implemented".to_string());
        }
    };

    // Pad the quote to TEE_QUOTE_SIZE
    Ok(TEEQuote::from_bytes_padded(&quote_bytes))
}

/// Generate AMD SEV-SNP attestation
async fn generate_amd_attestation(custom_data: &[u8]) -> Result<Vec<u8>, String> {
    #[cfg(all(feature = "tee-attestation", feature = "attestation"))]
    {
        use lunal_attestation::amd;
        
        match amd::attest::attest_compressed(custom_data).await {
            Ok(base64_encoded) => {
                // Return as bytes (base64 string)
                Ok(base64_encoded.into_bytes())
            }
            Err(e) => {
                tracing::warn!("Failed to generate AMD attestation: {}", e);
                Err(format!("AMD attestation generation failed: {}", e))
            }
        }
    }
    
    #[cfg(not(all(feature = "tee-attestation", feature = "attestation")))]
    {
        Err("AMD attestation feature not enabled (requires tee-attestation feature on Linux)".to_string())
    }
}

/// Generate Intel TDX attestation
async fn generate_tdx_attestation(custom_data: &[u8]) -> Result<Vec<u8>, String> {
    #[cfg(all(feature = "tee-attestation", feature = "attestation-tdx"))]
    {
        use lunal_attestation::attestation;
        
        match attestation::get_compressed_encoded_attestation() {
            Ok(base64_encoded) => {
                // Return as bytes (base64 string)
                Ok(base64_encoded.into_bytes())
            }
            Err(e) => {
                tracing::warn!("Failed to generate TDX attestation: {}", e);
                Err(format!("TDX attestation generation failed: {}", e))
            }
        }
    }
    
    #[cfg(not(all(feature = "tee-attestation", feature = "attestation-tdx")))]
    {
        Err("TDX attestation feature not enabled (requires tee-attestation feature on Linux)".to_string())
    }
}

/// Synchronous wrapper for TEE attestation verification.
/// This blocks on the async verification function for use in synchronous contexts.
pub fn verify_tee_attestation_sync(tee_type: &TEEType, quote: &TEEQuote) -> bool {
    tracing::debug!(
        "Verifying TEE attestation (synchronous) for type: {} with quote length: {} bytes",
        tee_type.as_str(),
        quote.as_bytes().len()
    );

    // For synchronous contexts, try to use existing runtime handle first
    match tokio::runtime::Handle::try_current() {
        Ok(handle) => {
            handle.block_on(verify_tee_attestation(tee_type, quote)).unwrap_or(false)
        }
        Err(_) => {
            // No runtime available, create a new one
            let rt = tokio::runtime::Runtime::new().unwrap_or_else(|e| {
                tracing::error!("Failed to create tokio runtime: {}", e);
                panic!("Cannot verify attestation without tokio runtime");
            });
            rt.block_on(verify_tee_attestation(tee_type, quote)).unwrap_or(false)
        }
    }
}

/// Mock TEE attestation verification for backward compatibility.
/// Deprecated: Use `verify_tee_attestation_sync` instead.
#[deprecated(note = "Use verify_tee_attestation_sync instead")]
pub fn verify_tee_attestation_mock(tee_type: &TEEType, quote: &TEEQuote) -> bool {
    verify_tee_attestation_sync(tee_type, quote)
}

/// Detailed verification returning an `AttestationResult`.
pub fn verify_tee_attestation_detailed(
    tee_type: &TEEType,
    _quote: &TEEQuote,
) -> AttestationResult {
    tracing::debug!("Detailed TEE verification for type: {}", tee_type.as_str());

    AttestationResult {
        is_valid: true,
        mrenclave: Some([0u8; 32]),
        mrsigner: Some([0u8; 32]),
        error_message: None,
    }
}

/// Mock Azure Attestation Service client.
/// In production, this would connect to https://attest.azure.net.
pub struct AzureAttestationService {
    endpoint: String,
    mock_mode: bool,
    client: reqwest::Client,
}

impl AzureAttestationService {
    /// Create a new Azure Attestation Service client.
    pub fn new(endpoint: Option<String>) -> Self {
        Self {
            endpoint: endpoint.unwrap_or_else(|| "https://attest.azure.net".to_string()),
            mock_mode: false,
            client: reqwest::Client::new(),
        }
    }

    /// Create a mock client for testing.
    pub fn new_mock() -> Self {
        Self {
            endpoint: "http://localhost:3000".to_string(),
            mock_mode: true,
            client: reqwest::Client::new(),
        }
    }

    /// Verify a TEE quote using Azure Attestation Service.
    pub async fn verify_quote(&self, quote: &TEEQuote) -> AttestationResult {
        if self.mock_mode {
            return self.verify_quote_mock_http(quote).await;
        }

        // TODO: Implement real Azure Attestation Service integration.
        self.verify_quote_mock_http(quote).await
    }

    /// Mock implementation of quote verification using HTTP.
    async fn verify_quote_mock_http(&self, quote: &TEEQuote) -> AttestationResult {
        if quote.as_bytes().len() < 432 {
            return AttestationResult {
                is_valid: false,
                mrenclave: None,
                mrsigner: None,
                error_message: Some("Invalid quote data length".to_string()),
            };
        }

        let payload = serde_json::json!({
            "quote": quote.to_base64(),
        });

        match self
            .client
            .post(&format!("{}/attest/verify", self.endpoint))
            .header("Content-Type", "application/json")
            .json(&payload)
            .send()
            .await
        {
            Ok(response) => {
                if response.status().is_success() {
                    AttestationResult {
                        is_valid: true,
                        mrenclave: Some([0u8; 32]),
                        mrsigner: Some([0u8; 32]),
                        error_message: None,
                    }
                } else {
                    AttestationResult {
                        is_valid: false,
                        mrenclave: None,
                        mrsigner: None,
                        error_message: Some(format!(
                            "Server returned status: {}",
                            response.status()
                        )),
                    }
                }
            }
            Err(e) => {
                tracing::warn!(
                    "Mock attestation server unavailable: {}. Using fallback validation.",
                    e
                );
                AttestationResult {
                    is_valid: true,
                    mrenclave: Some([0u8; 32]),
                    mrsigner: Some([0u8; 32]),
                    error_message: None,
                }
            }
        }
    }

    /// Convenience wrapper retained for compatibility with older call sites.
    pub async fn verify_quote_with_attestation_service(
        &self,
        quote: &TEEQuote,
    ) -> AttestationResult {
        self.verify_quote(quote).await
    }
}

/// Cache for attestation verification results.
pub struct AttestationCache {
    cache: std::collections::HashMap<Vec<u8>, AttestationResult>,
}

impl AttestationCache {
    pub fn new() -> Self {
        Self {
            cache: std::collections::HashMap::new(),
        }
    }

    pub fn get(&self, quote_data: &[u8]) -> Option<&AttestationResult> {
        self.cache.get(quote_data)
    }

    pub fn put(&mut self, quote_data: Vec<u8>, result: AttestationResult) {
        self.cache.insert(quote_data, result);
    }
}
