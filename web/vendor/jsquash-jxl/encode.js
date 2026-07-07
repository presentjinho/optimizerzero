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
 * Vendored + trimmed from @jsquash/jxl (jamsinclair/jSquash) for
 * OptimizerZero. Upstream's encode.js feature-detects WebAssembly threads
 * and SIMD via the `wasm-feature-detect` package and picks among 3 wasm
 * variants; we only ship the single-thread build (smaller vendor footprint,
 * one less dependency), so that branch is removed and this always loads
 * ./jxl_enc.js.
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
  const jxlEncoder = await import('./jxl_enc.js');
  emscriptenModule = initEmscriptenModule(jxlEncoder.default, actualModule, actualOptions);
  return emscriptenModule;
}

export default async function encode(data, options = {}) {
  if (!emscriptenModule) emscriptenModule = init();
  const module = await emscriptenModule;
  const _options = { ...defaultOptions, ...options };
  if (_options.lossless) {
    _options.quality = 100;
    _options.lossyModular = false;
    _options.lossyPalette = false;
  }
  const resultView = module.encode(data.data, data.width, data.height, _options);
  if (!resultView) {
    throw new Error('Encoding error.');
  }
  return resultView.buffer;
}
