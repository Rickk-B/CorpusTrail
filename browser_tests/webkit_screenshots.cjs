'use strict';
// Developer driver process only. No on-disk library or production-page changes.
const Module = require('node:module');
const crypto = require('node:crypto');
const path = require('node:path');
const target = process.env.CORPUSTRAIL_PLAYWRIGHT_BUNDLE;
const original = Module.prototype._compile;
const wanted = 'const syncAnimations = this._page.delegate.shouldToggleStyleSheetToSyncAnimations();';
Module.prototype._compile = function(content, filename) {
  if (target && path.resolve(filename) === target) {
    if (crypto.createHash('sha256').update(content).digest('hex') !== '549070af3acabb3efcc4f55bfe6210f9f7c2fcf633cf7eaa59bfe60719969171' || content.split(wanted).length !== 2)
      throw Error('Unreviewed Playwright screenshot driver; refusing adaptation');
    content = content.replace(wanted, 'const syncAnimations = false; // CorpusTrail: no inert inline style under strict CSP');
    Module.prototype._compile = original;
  }
  return original.call(this, content, filename);
};
