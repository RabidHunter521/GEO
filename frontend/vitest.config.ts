import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { defineConfig } from 'vitest/config';

import { storybookTest } from '@storybook/addon-vitest/vitest-plugin';

import { playwright } from '@vitest/browser-playwright';

const dirname =
  typeof __dirname !== 'undefined' ? __dirname : path.dirname(fileURLToPath(import.meta.url));

// More info at: https://storybook.js.org/docs/next/writing-tests/integrations/vitest-addon
export default defineConfig({
  oxc: false,
  esbuild: {
    jsx: "automatic",
  },
  resolve: {
    alias: {
      "@": path.resolve(dirname, "./src"),
      // src/lib/api.ts imports "server-only" so that pulling it into a client
      // bundle is a build error. Under Vitest there is no server/client graph,
      // so that package resolves to the variant that throws on import. Point it
      // at the no-op entry the package ships for exactly this case — the build
      // still gets the real guard; the tests can import the module under test.
      "server-only": path.resolve(dirname, "./node_modules/server-only/empty.js"),
    },
  },
  test: {
    projects: [
      {
        extends: true,
        plugins: [
          // The plugin will run tests for the stories defined in your Storybook config
          // See options at: https://storybook.js.org/docs/next/writing-tests/integrations/vitest-addon#storybooktest
          storybookTest({ configDir: path.join(dirname, '.storybook') }),
        ],
        test: {
          name: 'storybook',
          browser: {
            enabled: true,
            headless: true,
            provider: playwright({}),
            instances: [{ browser: 'chromium' }],
          },
        },
      },
      {
        extends: true,
        test: {
          name: "unit",
          environment: "node",
          include: ["src/lib/__tests__/**/*.test.ts"],
        },
      },
    ],
  },
});
