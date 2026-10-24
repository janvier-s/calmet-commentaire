// Entry point: the modules in order, then the first page.
import { ready, boot } from "./app.js";
import "./edit.js";
import "./queue.js";
import "./entries.js";

await ready;
await boot.start();
