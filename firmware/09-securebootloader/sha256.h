// SPDX-License-Identifier: MIT
/*!
****************************
\file       09-securebootloader/sha256.h
\brief      SHA-256 (FIPS 180-4) interface.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  Freestanding implementation: no libc, no heap. Usage: sha256_init(),
  sha256_update() any number of times, then sha256_final().

\section sha256_h_version_history Version history
| Version | Date       | Author      | Description                   |
|:-------:|:----------:|:------------|:------------------------------|
| 1.0     | 09/10/2026 | Z. BEN-AKKA | Initial version.              |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Comments per Contributing.md. |
****************************
*/

#ifndef SHA256_H
#define SHA256_H

#include <stddef.h>
#include <stdint.h>

#define SHA256_DIGEST_SIZE 32 ///< Digest length in bytes.

/// Hashing state, opaque to callers.
typedef struct {
  uint32_t state[8];
  uint64_t length; ///< Bytes hashed so far.
  uint8_t block[64];
  uint32_t used; ///< Bytes waiting in block.
} sha256_ctx;

/*!
\brief  Start a new hash.
\param  c  Context to initialise.
*/
void sha256_init(sha256_ctx *c);

/*!
\brief  Add data to the hash.
\param  c     Context.
\param  data  Bytes to hash.
\param  len   Number of bytes.
*/
void sha256_update(sha256_ctx *c, const void *data, size_t len);

/*!
\brief  Pad the message and produce the digest.
\param  c       Context; must be re-initialised before reuse.
\param  digest  Output, SHA256_DIGEST_SIZE bytes, big-endian.
*/
void sha256_final(sha256_ctx *c, uint8_t digest[SHA256_DIGEST_SIZE]);

#endif
