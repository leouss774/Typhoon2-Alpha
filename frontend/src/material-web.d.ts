// =============================================================================
//   @material/web — déclarations JSX pour React 19.
//   React 19 place le namespace JSX dans `declare namespace React` ; une simple
//   `declare namespace JSX` globale ne fusionne plus. On augmente donc le
//   module 'react' directement pour autoriser les éléments custom `md-*`.
// =============================================================================

import type {} from 'react';

declare module 'react' {
  namespace JSX {
    interface IntrinsicElements {
      [elemName: string]: any;
    }
  }
}
