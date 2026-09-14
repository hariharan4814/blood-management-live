import { defineNitroConfig } from "nitro/config";

export default defineNitroConfig({
  // This standalone service has no dependencies outside its frontend directory.
  traceOpts: { nft: { base: process.cwd() } },
});
