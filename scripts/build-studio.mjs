import { copyFile, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";

const output = "src/automeme/studio/static/vendor";

const files = {
  "filepond/dist/filepond.min.js": "filepond.min.js",
  "filepond/dist/filepond.min.css": "filepond.min.css",
  "lucide/dist/umd/lucide.min.js": "lucide.min.js",
  "plyr/dist/plyr.min.js": "plyr.min.js",
  "plyr/dist/plyr.css": "plyr.css",
  "plyr/dist/plyr.svg": "plyr.svg",
  "sortablejs/Sortable.min.js": "sortable.min.js",
  "wavesurfer.js/dist/wavesurfer.esm.js": "wavesurfer.mjs",
  "wavesurfer.js/dist/plugins/regions.esm.js": "wavesurfer-regions.mjs",
  "wavesurfer.js/dist/plugins/timeline.esm.js": "wavesurfer-timeline.mjs",
};

const licenses = {
  filepond: "LICENSE",
  lucide: "LICENSE",
  plyr: "LICENSE.md",
  sortablejs: "LICENSE",
  "wavesurfer.js": "LICENSE",
};

await rm(output, { recursive: true, force: true });
await mkdir(join(output, "licenses"), { recursive: true });

for (const [source, target] of Object.entries(files)) {
  const destination = join(output, target);
  await mkdir(dirname(destination), { recursive: true });
  await copyFile(join("node_modules", source), destination);
}

for (const [packageName, licenseName] of Object.entries(licenses)) {
  await copyFile(
    join("node_modules", packageName, licenseName),
    join(output, "licenses", `${packageName}.txt`),
  );
}
