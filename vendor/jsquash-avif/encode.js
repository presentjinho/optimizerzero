/**
 * Copyright 2020 Google Inc. All Rights Reserved.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     http://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Vendored + trimmed from @jsquash/avif (jamsinclair/jSquash) for
 * OptimizerZero. Upstream's encode.js feature-detects WebAssembly threads
 * via the `wasm-feature-detect` package and picks a multi-threaded wasm
 * variant; we only ship the single-thread build (smaller vendor footprint,
 * one less dependency), so that branch is removed and this always loads
 * ./avif_enc.js.
 */
import { defaultOptions } from './meta.js';
import { initEmscriptenModule } from './utils.js';

let emscriptenModule;

export async function init(module, moduleOptionOverrides) {
  let actualModule = module;
  let actualOptions = moduleOptionOverrides;
  if (arguments.length === 1 && !(module instanceof WebAssembly.Module)) {
    actualModule = undefined;
    actualOptions = module;
  }
  const avifEncoder = await import('./avif_enc.js');
  emscriptenModule = initEmscriptenModule(avifEncoder.default, actualModule, actualOptions);
  return emscriptenModule;
}

export default async function encode(data, options = {}) {
  if (!emscriptenModule) emscriptenModule = init();
  const _options = { ...defaultOptions, ...options };
  if (_options.bitDepth !== 8 && _options.bitDepth !== 10 && _options.bitDepth !== 12) {
    throw new Error('Invalid bit depth. Supported values are 8, 10, or 12.');
  }
  if (!(data.data instanceof Uint16Array) && _options.bitDepth !== 8) {
    throw new Error('Invalid image data for bit depth. Must use Uint16Array for bit depths greater than 8.');
  }
  if (_options.lossless) {
    _options.quality = 100;
    _options.qualityAlpha = -1;
    _options.subsample = 3;
  }
  const module = await emscriptenModule;
  const output = module.encode(new Uint8Array(data.data.buffer), data.width, data.height, _options);
  if (!output) {
    throw new Error('Encoding error.');
  }
  return output.buffer;
}
