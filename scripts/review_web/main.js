// Entry point: the modules in order, then the first page.
import { ready, boot } from "./app.js";
import "./edit.js";
import "./queue.js";
import "./entries.js";
import "./point.js";
import "./turn.js";
import "./proposal.js";
import "./batch.js";
import "./search.js";
import "./tags.js";
import "./todo.js";
import "./reviewed.js";
import "./watch.js";
import "./ocr.js";
import { decorate } from "./icons.js";

decorate();

await ready;
await boot.start();
