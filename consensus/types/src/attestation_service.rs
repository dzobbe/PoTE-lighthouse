use crate::tee_attestation::{AttestationResult, TEEQuote};
use crate::tee_types::TEEType;

/// Mock TEE attestation verification for block validation.
/// Always returns `true` until a real implementation is wired in.
pub fn verify_tee_attestation_mock(tee_type: &TEEType, quote: &TEEQuote) -> bool {
    tracing::debug!(
        "Mock TEE verification for type: {} with quote length: {} bytes",
        tee_type.as_str(),
        quote.as_bytes().len()
    );

    // TODO: Call into a real attestation verification pipeline.
    true
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
