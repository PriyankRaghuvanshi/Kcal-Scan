module.exports = {
  testEnvironment: "node",
  testMatch: ["**/__tests__/**/*.test.js"],
  setupFiles: ["<rootDir>/jest.setup.js"],
  transform: { "\\.js$": "babel-jest" },
  transformIgnorePatterns: [
    "node_modules/(?!(react-native|@react-native|expo|expo-.*|@expo/.*)/)",
  ],
};
