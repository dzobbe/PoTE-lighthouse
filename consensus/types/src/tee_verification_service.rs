use crate::tee_attestation::TEEQuote;
use crate::tee_types::TEEType;
use crate::attestation_service::verify_tee_attestation;
use std::sync::Arc;
use std::sync::OnceLock;
use tokio::runtime::{Handle, Runtime};
use tokio::sync::Semaphore;
use tracing::{info, warn};

/// Shared TEE verification service that reuses a tokio runtime
/// and supports async verification, batching, and background verification
pub struct TeeVerificationService {
    /// Shared tokio runtime handle for verification tasks
    runtime_handle: Handle,
    /// Optional runtime that we keep alive if we created it
    /// This ensures the handle remains valid
    _runtime: Option<Arc<Runtime>>,
    /// Semaphore to limit concurrent verifications
    concurrency_limit: Arc<Semaphore>,
}

impl TeeVerificationService {
    /// Create a new TEE verification service with a shared runtime
    pub fn new(max_concurrent: usize) -> Result<Self, String> {
        // Try to get the current runtime handle first
        let (runtime_handle, runtime) = match Handle::try_current() {
            Ok(handle) => {
                info!("Using existing tokio runtime for TEE verification");
                (handle, None)
            }
            Err(_) => {
                // Create a dedicated runtime for TEE verification
                // We must keep the runtime alive or the handle becomes invalid
                warn!("No tokio runtime found, creating dedicated runtime for TEE verification");
                let runtime = Arc::new(
                    Runtime::new()
                        .map_err(|e| format!("Failed to create tokio runtime: {}", e))?
                );
                let handle = runtime.handle().clone();
                (handle, Some(runtime))
            }
        };

        let concurrency_limit = Arc::new(Semaphore::new(max_concurrent));

        Ok(Self {
            runtime_handle,
            _runtime: runtime,
            concurrency_limit,
        })
    }

    /// Verify a single TEE attestation asynchronously
    pub async fn verify_async(
        &self,
        tee_type: &TEEType,
        quote: &TEEQuote,
    ) -> Result<bool, String> {
        let tee_type = tee_type.clone();
        let quote = quote.clone();
        let _permit = self.concurrency_limit.acquire().await
            .map_err(|e| format!("Failed to acquire semaphore permit: {}", e))?;

        // Verify directly using the async function
        verify_tee_attestation(&tee_type, &quote).await
    }

    /// Verify multiple TEE attestations in parallel (batch verification)
    /// Note: Due to Send constraints, we use spawn_blocking for each verification
    pub async fn verify_batch(
        &self,
        verifications: Vec<(TEEType, TEEQuote)>,
    ) -> Vec<Result<bool, String>> {
        let service = Arc::new(self.clone());
        let mut handles = Vec::new();

        for (tee_type, quote) in verifications {
            let service_clone = service.clone();
            // Use spawn_blocking since verify_tee_attestation may not be Send
            let handle = tokio::task::spawn_blocking(move || {
                let runtime_handle = service_clone.runtime_handle.clone();
                let concurrency_limit = service_clone.concurrency_limit.clone();
                
                runtime_handle.block_on(async {
                    let _permit = concurrency_limit.acquire().await
                        .map_err(|e| format!("Failed to acquire semaphore permit: {}", e))?;
                    verify_tee_attestation(&tee_type, &quote).await
                })
            });
            handles.push(handle);
        }

        // Wait for all verifications to complete
        let mut results = Vec::new();
        for handle in handles {
            match handle.await {
                Ok(result) => results.push(result),
                Err(e) => results.push(Err(format!("Task panicked: {:?}", e))),
            }
        }
        results
    }

    /// Start background verification (lazy verification)
    /// Returns immediately with a handle to check verification status later
    /// Note: This does NOT cache results - each verification is fresh
    /// Note: Uses spawn_blocking due to Send constraints
    pub fn verify_background(
        &self,
        tee_type: TEEType,
        quote: TEEQuote,
    ) -> tokio::task::JoinHandle<Result<bool, String>> {
        let runtime_handle = self.runtime_handle.clone();
        let concurrency_limit = self.concurrency_limit.clone();

        // Use spawn_blocking since verify_tee_attestation may not be Send
        tokio::task::spawn_blocking(move || {
            runtime_handle.block_on(async {
                let _permit = concurrency_limit.acquire().await
                    .map_err(|e| format!("Failed to acquire semaphore permit: {}", e))?;
                
                verify_tee_attestation(&tee_type, &quote).await
            })
        })
    }

    /// Verify synchronously (for backward compatibility)
    /// Uses the shared runtime instead of creating a new one per verification
    /// Note: This should be called from a blocking context (e.g., spawn_blocking_handle)
    /// If called from an async context, use verify_async instead
    pub fn verify_sync(&self, tee_type: &TEEType, quote: &TEEQuote) -> bool {
        let tee_type = tee_type.clone();
        let quote = quote.clone();
        let runtime_handle = self.runtime_handle.clone();
        let concurrency_limit = self.concurrency_limit.clone();

        // We're already in a blocking context (from spawn_blocking_handle),
        // so we can directly block_on without block_in_place overhead
        runtime_handle.block_on(async {
            let permit = concurrency_limit.acquire().await.ok();
            if permit.is_none() {
                return false;
            }
            verify_tee_attestation(&tee_type, &quote).await.unwrap_or(false)
        })
    }
}

// Implement Clone for Arc-wrapping
impl Clone for TeeVerificationService {
    fn clone(&self) -> Self {
        Self {
            runtime_handle: self.runtime_handle.clone(),
            _runtime: self._runtime.clone(),
            concurrency_limit: self.concurrency_limit.clone(),
        }
    }
}

impl Default for TeeVerificationService {
    fn default() -> Self {
        Self::new(10).expect("Failed to create default TEE verification service")
    }
}

/// Global TEE verification service instance
/// This is initialized once and reused across all verifications
static GLOBAL_TEE_VERIFICATION_SERVICE: OnceLock<Arc<TeeVerificationService>> = OnceLock::new();

/// Get the global TEE verification service
/// Initializes it on first call if not already initialized
pub fn get_global_service() -> Arc<TeeVerificationService> {
    GLOBAL_TEE_VERIFICATION_SERVICE
        .get_or_init(|| {
            Arc::new(
                TeeVerificationService::new(10)
                    .expect("Failed to initialize global TEE verification service")
            )
        })
        .clone()
}

