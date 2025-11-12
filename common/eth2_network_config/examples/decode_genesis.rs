use std::env;
use std::path::PathBuf;

use eth2_network_config::Eth2NetworkConfig;
use types::{BeaconState, MainnetEthSpec};

fn main() {
    let mut args = env::args().skip(1);
    let path = args
        .next()
        .expect("provide path to genesis SSZ as first argument");

    let bytes = std::fs::read(PathBuf::from(path)).expect("unable to read genesis file");

    let config = Eth2NetworkConfig::constant("mainnet")
        .expect("load built-in config")
        .expect("mainnet config not embedded");

    let spec = config
        .chain_spec::<MainnetEthSpec>()
        .expect("obtain mainnet chain spec");

    match BeaconState::<MainnetEthSpec>::from_ssz_bytes(bytes.as_slice(), &spec) {
        Ok(_) => println!("Successfully decoded beacon state ({} bytes)", bytes.len()),
        Err(e) => {
            println!(
                "Failed to decode beacon state ({} bytes): {:?}",
                bytes.len(),
                e
            );
        }
    }
}
