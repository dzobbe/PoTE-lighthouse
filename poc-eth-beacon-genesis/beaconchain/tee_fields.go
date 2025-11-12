package beaconchain

import (
	"encoding/base64"
	"fmt"

	"github.com/attestantio/go-eth2-client/spec/phase0"

	"github.com/ethpandaops/eth-beacon-genesis/beaconconfig"
)

const (
	teeVendorMin = 0
	teeVendorMax = 2
)

// getGenesisProposerTEEFields resolves the proposer TEE metadata that should be embedded in the
// genesis block header. It prefers a dedicated TEE_PROPOSER_VENDOR override and falls back to the
// global TEE_VENDOR default that is already used for validators. Optional attestation quote data can be
// supplied via TEE_PROPOSER_ATTESTATION as a base64-encoded string; legacy byte inputs are converted to
// base64 automatically.
func getGenesisProposerTEEFields(cfg *beaconconfig.Config) (phase0.TEEType, [phase0.ProposerTEEQuoteSize]byte, error) {
	var emptyQuote [phase0.ProposerTEEQuoteSize]byte

	defaultVendor := cfg.GetUintDefault("TEE_VENDOR", teeVendorMin)
	if defaultVendor < teeVendorMin || defaultVendor > teeVendorMax {
		return 0, emptyQuote, fmt.Errorf("invalid TEE_VENDOR value: %d (must be between %d and %d)", defaultVendor, teeVendorMin, teeVendorMax)
	}

	proposerVendor := cfg.GetUintDefault("TEE_PROPOSER_VENDOR", defaultVendor)
	if proposerVendor < teeVendorMin || proposerVendor > teeVendorMax {
		return 0, emptyQuote, fmt.Errorf("invalid TEE_PROPOSER_VENDOR value: %d (must be between %d and %d)", proposerVendor, teeVendorMin, teeVendorMax)
	}

	var quoteString string
	if str, ok := cfg.GetString("TEE_PROPOSER_ATTESTATION"); ok {
		quoteString = str
	} else if bytes, ok := cfg.GetBytes("TEE_PROPOSER_ATTESTATION"); ok {
		quoteString = base64.StdEncoding.EncodeToString(bytes)
	}

	var quoteBytes [phase0.ProposerTEEQuoteSize]byte
	if quoteString != "" {
		decoded, err := base64.StdEncoding.DecodeString(quoteString)
		if err != nil {
			return 0, emptyQuote, fmt.Errorf("TEE_PROPOSER_ATTESTATION invalid base64: %w", err)
		}
		if len(decoded) != phase0.ProposerTEEQuoteSize {
			return 0, emptyQuote, fmt.Errorf(
				"TEE_PROPOSER_ATTESTATION decoded length mismatch: got %d bytes, expected %d",
				len(decoded),
				phase0.ProposerTEEQuoteSize,
			)
		}
		copy(quoteBytes[:], decoded)
	}

	return phase0.TEEType(proposerVendor), quoteBytes, nil
}

