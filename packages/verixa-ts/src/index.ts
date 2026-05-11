/**
 * Verixa shared TypeScript library.
 *
 * Cross-cutting types, constants, helpers + the public TypeScript SDK
 * used by the Control Plane UI and any other Verixa TypeScript consumers.
 * Mirrors `packages/verixa-python` where applicable.
 *
 * Typed response envelopes (re-exported from envelopes.ts) added in
 * CP-65; cross-language symmetry with Python CP-61..CP-64.
 */

export * from './compliance-language.js';
export * from './envelopes.js';
export * from './sdk.js';

export const VERIXA_TS_VERSION = '0.2.0';
