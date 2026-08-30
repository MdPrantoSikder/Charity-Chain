const { ethers } = require("ethers");
const fs = require("fs");
const path = require("path");

async function main() {
  console.log("🚀 Starting isolated low-level deployment...");
  const provider = new ethers.JsonRpcProvider("http://127.0.0.1:8545");
  const privKey = "8f2a55949038a9610f50fb23b5883af3b4ecb3c3bb792cbcefbd1542c692be63";

  const signingKey = new ethers.SigningKey("0x" + privKey);
  const trueAddress = ethers.computeAddress(signingKey.publicKey);
  console.log("Calculated Deployer Address:", trueAddress);

  const wallet = new ethers.Wallet(privKey, provider);
  const artifactPath = path.join(__dirname, "../artifacts/contracts/CharityChain.sol/CharityChain.json");
  const artifact = require(artifactPath);

  console.log("Broadcasting bytecode directly to Besu network...");
  const factory = new ethers.ContractFactory(artifact.abi, artifact.bytecode, wallet);
  const contract = await factory.deploy();
  await contract.waitForDeployment();
  const address = await contract.getAddress();

  console.log("✅ CharityChain successfully deployed at:", address);

  // Save contract_info.json
  const output = {
    contract_address: address,
    deployer_address: wallet.address,
    network: "hyperledger-besu",
    chain_id: 1337,
    abi: artifact.abi
  };
  fs.writeFileSync(path.join(__dirname, "../contract_info.json"), JSON.stringify(output, null, 2));

  // ✅ Auto-update backend .env with new CONTRACT_ADDRESS
  const envPath = path.join(__dirname, "../../backend/.env");
  let env = fs.readFileSync(envPath, "utf8");
  env = env.replace(/CONTRACT_ADDRESS=.*/,  `CONTRACT_ADDRESS=${address}`);
  fs.writeFileSync(envPath, env);
  console.log("✅ .env updated automatically → CONTRACT_ADDRESS=" + address);

  console.log("CONTRACT_ADDRESS=" + address);
}

main().catch((err) => { console.error(err); process.exit(1); });