module.exports = {
  extends: ["@commitlint/config-conventional"],
  // Bot PR descriptions are not conventional-commit bodies, so do not lint them.
  ignores: [
    // Renovate
    (message) => /^This PR contains the following updates:$/m.test(message),
  ],
  rules: {
    "body-max-line-length": [0, "always", Infinity],
    "footer-max-line-length": [0, "always", Infinity],
    "body-leading-blank": [0, "always"],
  },
};
