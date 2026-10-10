// SPDX-License-Identifier: MIT
/*!
****************************
\file       09-securebootloader/sha256.c
\brief      SHA-256 (FIPS 180-4) implementation.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  64-byte blocks, each expanded to 64 words and mixed into the 8-word state
  by 64 rounds. Bytes are fed one at a time: written for clarity, not speed.
  API documented in sha256.h.

\section sha256_c_version_history Version history
| Version | Date       | Author      | Description                   |
|:-------:|:----------:|:------------|:------------------------------|
| 1.0     | 09/10/2026 | Z. BEN-AKKA | Initial version.              |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Comments per Contributing.md. |
****************************
*/

#include "sha256.h"

// Round constants: fractional parts of the cube roots of the first 64 primes
static const uint32_t K[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

#define ROTR(x, n) (((x) >> (n)) | ((x) << (32 - (n))))

/*!
\brief  Process one 64-byte block into the state.
*/
static void compress(uint32_t s[8], const uint8_t *p)
{
  uint32_t w[64];

  for (int i = 0; i < 16; i++) {
    w[i] = (uint32_t)p[4 * i] << 24 | (uint32_t)p[4 * i + 1] << 16 | (uint32_t)p[4 * i + 2] << 8 |
           (uint32_t)p[4 * i + 3];
  }
  for (int i = 16; i < 64; i++) {
    uint32_t s0 = ROTR(w[i - 15], 7) ^ ROTR(w[i - 15], 18) ^ (w[i - 15] >> 3);
    uint32_t s1 = ROTR(w[i - 2], 17) ^ ROTR(w[i - 2], 19) ^ (w[i - 2] >> 10);
    w[i] = w[i - 16] + s0 + w[i - 7] + s1;
  }

  uint32_t a = s[0], b = s[1], c = s[2], d = s[3];
  uint32_t e = s[4], f = s[5], g = s[6], h = s[7];

  for (int i = 0; i < 64; i++) {
    uint32_t S1 = ROTR(e, 6) ^ ROTR(e, 11) ^ ROTR(e, 25);
    uint32_t ch = (e & f) ^ (~e & g);
    uint32_t t1 = h + S1 + ch + K[i] + w[i];
    uint32_t S0 = ROTR(a, 2) ^ ROTR(a, 13) ^ ROTR(a, 22);
    uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
    uint32_t t2 = S0 + maj;

    h = g;
    g = f;
    f = e;
    e = d + t1;
    d = c;
    c = b;
    b = a;
    a = t1 + t2;
  }

  s[0] += a;
  s[1] += b;
  s[2] += c;
  s[3] += d;
  s[4] += e;
  s[5] += f;
  s[6] += g;
  s[7] += h;
}

void sha256_init(sha256_ctx *c)
{
  // Initial state: fractional parts of the square roots of the first 8 primes
  c->state[0] = 0x6a09e667;
  c->state[1] = 0xbb67ae85;
  c->state[2] = 0x3c6ef372;
  c->state[3] = 0xa54ff53a;
  c->state[4] = 0x510e527f;
  c->state[5] = 0x9b05688c;
  c->state[6] = 0x1f83d9ab;
  c->state[7] = 0x5be0cd19;
  c->length = 0;
  c->used = 0;
}

void sha256_update(sha256_ctx *c, const void *data, size_t len)
{
  const uint8_t *p = data;

  c->length += len;
  while (len--) {
    c->block[c->used++] = *p++;
    if (c->used == 64) {
      compress(c->state, c->block);
      c->used = 0;
    }
  }
}

void sha256_final(sha256_ctx *c, uint8_t digest[SHA256_DIGEST_SIZE])
{
  uint64_t bits = c->length * 8;

  c->block[c->used++] = 0x80;
  if (c->used > 56) { // no room left for the length
    while (c->used < 64) {
      c->block[c->used++] = 0;
    }
    compress(c->state, c->block);
    c->used = 0;
  }
  while (c->used < 56) {
    c->block[c->used++] = 0;
  }
  for (int i = 0; i < 8; i++) {
    c->block[56 + i] = (uint8_t)(bits >> (56 - 8 * i));
  }
  compress(c->state, c->block);

  for (int i = 0; i < 8; i++) {
    digest[4 * i] = (uint8_t)(c->state[i] >> 24);
    digest[4 * i + 1] = (uint8_t)(c->state[i] >> 16);
    digest[4 * i + 2] = (uint8_t)(c->state[i] >> 8);
    digest[4 * i + 3] = (uint8_t)(c->state[i]);
  }
}
