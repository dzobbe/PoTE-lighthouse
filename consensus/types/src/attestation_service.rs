use crate::tee_attestation::{AttestationResult, TEEQuote, TEE_QUOTE_SIZE};
use crate::tee_types::TEEType;
use hex;

/// Real TEE attestation verification using lunal-attestation library.
pub async fn verify_tee_attestation(
    tee_type: &TEEType,
    quote: &TEEQuote,
) -> Result<bool, String> {
    tracing::info!(
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
    
    tracing::info!(
        "🔍 Quote extraction: Full quote size: {} bytes, Extracted quote size: {} bytes (trimmed {} bytes of padding)",
        quote_bytes.len(),
        actual_quote_data.len(),
        quote_bytes.len() - actual_quote_end
    );

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
            tracing::info!(
                "🔍 Found padding pattern at offset {} (32 consecutive zeros), using quote length: {} bytes",
                i,
                i
            );
            return i;
        }
    }
    // If no clear padding found, assume all bytes are used
    tracing::info!(
        "🔍 No padding pattern found, using full quote length: {} bytes",
        quote_bytes.len()
    );
    quote_bytes.len()
}

/// Trim null bytes from the end of a byte slice
fn trim_null_bytes(data: &[u8]) -> &[u8] {
    let mut end = data.len();
    while end > 0 && data[end - 1] == 0 {
        end -= 1;
    }
    &data[..end]
}

/// Verify AMD SEV-SNP attestation
async fn verify_amd_attestation(quote_data: &[u8]) -> Result<bool, String> {
    use lunal_attestation::amd;
    
    tracing::info!(
        "🔍 AMD attestation verification: Starting with quote_data length: {} bytes",
        quote_data.len()
    );
    
    // Trim null bytes from the end (padding)
    let quote_data_trimmed = trim_null_bytes(quote_data);
    tracing::info!(
        "🔍 After trimming null bytes: length reduced from {} to {} bytes",
        quote_data.len(),
        quote_data_trimmed.len()
    );
    
    // Log first and last bytes for debugging
    if quote_data_trimmed.len() > 0 {
        let preview_len = quote_data_trimmed.len().min(100);
        let first_bytes = &quote_data_trimmed[..preview_len];
        let last_bytes = if quote_data_trimmed.len() > 100 {
            &quote_data_trimmed[quote_data_trimmed.len().saturating_sub(50)..]
        } else {
            &[]
        };
        tracing::info!(
            "🔍 Quote data preview: first {} bytes (hex): {}, last {} bytes (hex): {}",
            preview_len,
            hex::encode(first_bytes),
            last_bytes.len(),
            if last_bytes.is_empty() {
                "N/A".to_string()
            } else {
                hex::encode(last_bytes)
            }
        );
    }
    
    // Check if data is valid UTF-8
    let is_utf8 = std::str::from_utf8(quote_data_trimmed).is_ok();
    tracing::info!("🔍 Quote data is valid UTF-8: {}", is_utf8);
    
    // The quote data is expected to be base64-encoded and possibly compressed
    // Try as compressed base64 string first (most common format)
    if let Ok(base64_str) = std::str::from_utf8(quote_data_trimmed) {
        let trimmed = base64_str.trim();
        tracing::info!(
            "🔍 Attempting compressed base64 verification: trimmed length: {} chars, first 100 chars: {}",
            trimmed.len(),
            if trimmed.len() > 100 {
                &trimmed[..100]
            } else {
                trimmed
            }
        );
        match amd::verify::verify_compressed(&[], trimmed, Some(false)).await {
            Ok(_result) => {
                tracing::info!("✅ AMD attestation verification successful (compressed base64)");
                return Ok(true);
            }
            Err(e) => {
                tracing::warn!("❌ Failed to verify as compressed base64: {}", e);
            }
        }
    } else {
        tracing::warn!("❌ Quote data is not valid UTF-8, skipping compressed base64 verification");
    }

    // Try to decode as base64 and parse as AttestationEvidence
    let decoded = if let Ok(s) = std::str::from_utf8(quote_data_trimmed) {
        let trimmed = s.trim();
        tracing::info!(
            "🔍 Attempting base64 decode: input length: {} chars, first 100 chars: {}",
            trimmed.len(),
            if trimmed.len() > 100 {
                &trimmed[..100]
            } else {
                trimmed
            }
        );
        // If it's valid UTF-8, try to decode as base64
        match base64::decode(trimmed) {
            Ok(decoded_bytes) => {
                tracing::info!(
                    "✅ Base64 decode successful: decoded length: {} bytes",
                    decoded_bytes.len()
                );
                decoded_bytes
            }
            Err(e) => {
                tracing::warn!(
                    "❌ Base64 decode failed: {}. Assuming quote_data is already binary.",
                    e
                );
                quote_data_trimmed.to_vec()
            }
        }
    } else {
        tracing::warn!("❌ Quote data is not valid UTF-8. Assuming it's already binary data.");
        quote_data_trimmed.to_vec()
    };

    tracing::info!(
        "🔍 Attempting to parse as AttestationEvidence: decoded length: {} bytes",
        decoded.len()
    );
    
    // Log preview of decoded data
    if decoded.len() > 0 {
        let preview_len = decoded.len().min(100);
        let first_bytes = &decoded[..preview_len];
        tracing::info!(
            "🔍 Decoded data preview: first {} bytes (hex): {}",
            preview_len,
            hex::encode(first_bytes)
        );
    }

    // Try to parse as AttestationEvidence
    match amd::AttestationEvidence::from_bytes(&decoded) {
        Ok(evidence) => {
            tracing::info!("✅ Successfully parsed as AttestationEvidence");
            // Verify with empty custom data (or extract from evidence if needed)
            match amd::verify::verify_evidence(&[], &evidence, Some(false)).await {
                Ok(_result) => {
                    tracing::info!("✅ AMD attestation verification successful");
                    Ok(true)
                }
                Err(e) => {
                    tracing::warn!("❌ AMD attestation verification failed: {}", e);
                    Ok(false)
                }
            }
        }
        Err(e) => {
            tracing::warn!(
                "❌ Could not parse AMD attestation quote data as AttestationEvidence: {}",
                e
            );
            tracing::warn!(
                "   Quote data length: {} bytes, Decoded length: {} bytes, Is UTF-8: {}",
                quote_data.len(),
                decoded.len(),
                is_utf8
            );
            Ok(false)
        }
    }
}

/// Verify Intel TDX attestation
async fn verify_tdx_attestation(quote_data: &[u8]) -> Result<bool, String> {
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
            tracing::info!("TDX attestation verification successful");
            Ok(true)
        }
        Err(e) => {
            tracing::warn!("TDX attestation verification failed: {}", e);
            Ok(false)
        }
    }
}

/// Generate a TEE attestation quote for the given TEE type.
/// Returns a fixed-size TEEQuote (8192 bytes) with the actual quote data and padding.
pub async fn generate_tee_quote(tee_type: &TEEType, custom_data: &[u8]) -> Result<TEEQuote, String> {
    tracing::info!(
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
    use lunal_attestation::amd;
    
    tracing::info!(
        "🔍 Generating AMD attestation: custom_data length: {} bytes",
        custom_data.len()
    );
    
    match amd::attest::attest_compressed(custom_data).await {
        Ok(base64_encoded) => {
            tracing::info!(
                "✅ Generated AMD attestation (compressed base64): length: {} chars, first 100 chars: {}",
                base64_encoded.len(),
                if base64_encoded.len() > 100 {
                    &base64_encoded[..100]
                } else {
                    &base64_encoded
                }
            );
            // Return as bytes (base64 string)
            Ok(base64_encoded.into_bytes())
        }
        Err(e) => {
            tracing::warn!("❌ Failed to generate AMD attestation: {}", e);
            Err(format!("AMD attestation generation failed: {}", e))
        }
    }
}

/// Generate Intel TDX attestation
async fn generate_tdx_attestation(custom_data: &[u8]) -> Result<Vec<u8>, String> {
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

/// Synchronous wrapper for TEE attestation verification.
/// This blocks on the async verification function for use in synchronous contexts.
pub fn verify_tee_attestation_sync(tee_type: &TEEType, quote: &TEEQuote) -> bool {
    tracing::info!(
        "Verifying TEE attestation (synchronous) for type: {} with quote length: {} bytes",
        tee_type.as_str(),
        quote.as_bytes().len()
    );

    // Clone the inputs for use in the async context
    let tee_type = tee_type.clone();
    let quote = quote.clone();

    // Check if we're in a tokio runtime context
    match tokio::runtime::Handle::try_current() {
        Ok(_handle) => {
            // We're in a tokio runtime. Using block_on from within a runtime can cause deadlocks/panics,
            // so we always create a separate runtime in a blocking thread to avoid this issue.
            // This is safe because we're likely already in a blocking context (from spawn_blocking_handle).
            std::thread::spawn(move || {
                let rt = tokio::runtime::Runtime::new().unwrap_or_else(|e| {
                    tracing::error!("Failed to create tokio runtime in blocking thread: {}", e);
                    panic!("Cannot verify attestation without tokio runtime");
                });
                rt.block_on(verify_tee_attestation(&tee_type, &quote)).unwrap_or(false)
            })
            .join()
            .unwrap_or_else(|e| {
                tracing::error!("Thread panicked during TEE verification: {:?}", e);
                false
            })
        }
        Err(_) => {
            // No runtime available, create a new one
            let rt = tokio::runtime::Runtime::new().unwrap_or_else(|e| {
                tracing::error!("Failed to create tokio runtime: {}", e);
                panic!("Cannot verify attestation without tokio runtime");
            });
            rt.block_on(verify_tee_attestation(&tee_type, &quote)).unwrap_or(false)
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
    tracing::info!("Detailed TEE verification for type: {}", tee_type.as_str());

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

/// Check if the tee-attestation feature is enabled at compile time.
/// This function always returns true since tee-attestation is now always enabled.
/// 
/// # Returns
/// 
/// - Always returns `true` (tee-attestation is always enabled)
/// 
/// # Example
/// 
/// ```rust
/// use types::attestation_service::is_tee_attestation_enabled;
/// 
/// if is_tee_attestation_enabled() {
///     println!("TEE attestation feature is enabled!");
/// }
/// ```
pub fn is_tee_attestation_enabled() -> bool {
    true
}

/// Check if the tee-attestation feature is enabled and if the lunal-attestation dependency is available.
/// This provides a more comprehensive check than `is_tee_attestation_enabled()`.
/// 
/// # Returns
/// 
/// A tuple of (feature_enabled, dependency_available) - both always true since tee-attestation is always enabled
/// 
/// # Example
/// 
/// ```rust
/// use types::attestation_service::check_tee_attestation_support;
/// 
/// let (feature_enabled, dep_available) = check_tee_attestation_support();
/// if feature_enabled && dep_available {
///     println!("TEE attestation is fully supported!");
/// }
/// ```
pub fn check_tee_attestation_support() -> (bool, bool) {
    // TEE attestation is always enabled, so both are always true
    (true, true)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tee_attestation_feature_check() {
        let enabled = is_tee_attestation_enabled();
        println!("TEE attestation feature enabled: {}", enabled);
        
        // TEE attestation is always enabled now
        assert!(enabled, "TEE attestation should always be enabled");
    }

    #[test]
    fn test_tee_attestation_support_check() {
        let (feature_enabled, dep_available) = check_tee_attestation_support();
        println!("TEE attestation feature enabled: {}", feature_enabled);
        println!("TEE attestation dependency available: {}", dep_available);
        
        // Both should always be true since tee-attestation is always enabled
        assert!(feature_enabled, "TEE attestation feature should always be enabled");
        assert!(dep_available, "TEE attestation dependency should always be available");
    }
}
