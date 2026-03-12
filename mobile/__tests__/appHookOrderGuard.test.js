const fs = require('fs');
const path = require('path');

describe('App hook order guard', () => {
  test('does not declare hooks after the unauthenticated early return block', () => {
    const appPath = path.join(__dirname, '..', 'App.js');
    const source = fs.readFileSync(appPath, 'utf8');

    const earlyReturnIndex = source.indexOf('// ===================== RENDER: LOGIN =====================');
    expect(earlyReturnIndex).toBeGreaterThan(0);

    const postLoginSource = source.slice(earlyReturnIndex);
    const lateHookMatches = postLoginSource.match(/\buse(Effect|State|Memo|Ref|Callback|Reducer|LayoutEffect)\s*\(/g) || [];

    expect(lateHookMatches).toEqual([]);
  });
});
