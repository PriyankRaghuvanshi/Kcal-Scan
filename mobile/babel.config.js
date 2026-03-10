module.exports = function (api) {
  api.cache(true);
  const isTest = process.env.NODE_ENV === "test";
  return {
    presets: [
      isTest ? ["@babel/preset-env", { targets: { node: "current" } }] : "babel-preset-expo",
    ],
  };
};
