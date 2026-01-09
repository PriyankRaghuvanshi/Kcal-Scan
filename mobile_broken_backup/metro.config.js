const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

// Disable file system watching completely
config.watchFolders = [];
config.resolver.blockList = [
  /.*\/node_modules\/.*/,
  /.*\/\.git\/.*/,
  /.*\/\.expo\/.*/
];

module.exports = config;
