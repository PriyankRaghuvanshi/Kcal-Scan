const jwt = require("jsonwebtoken");
const fs = require("fs");

// ---- REPLACE THESE ----
const teamId = "V72HBA46M8";
const clientId = "com.priyank.calorieclick.service"; // e.g. com.priyank.calorieclick
const keyId = "29TA7SA69C";
const privateKeyPath = "/Users/priyankraghuvanshi/kcal-photo-app/keys/AuthKey_29TA7SA69C.p8"; // your downloaded .p8 file
// -----------------------

const privateKey = fs.readFileSync(privateKeyPath);

const token = jwt.sign(
  {},
  privateKey,
  {
    algorithm: "ES256",
    expiresIn: "180d", // 6 months max allowed
    audience: "https://appleid.apple.com",
    issuer: teamId,
    subject: clientId,
    keyid: keyId,
  }
);

console.log(token);
