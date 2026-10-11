// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/boot/boot.h
\brief      Hand-over from a bootloader to an application image.

\author     Z. BEN-AKKA
\version    1.0
\date       10/10/2026

\details
  An application image starts with its vector table: word 0 is the initial
  stack pointer, word 1 the reset handler address (Thumb bit set).

\section boot_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef BOOT_H
#define BOOT_H

#include <stdint.h>

/*!
\brief  Check that a vector table looks like one of our applications.
\param  sp    Initial stack pointer (word 0).
\param  pc    Reset handler address (word 1).
\param  base  Start of the application region.
\param  size  Size of the application region, in bytes.
\return Non-zero if SP is in RAM and PC is a Thumb address inside the region.
*/
int BootAppLooksValid(uint32_t sp, uint32_t pc, uint32_t base, uint32_t size);

/*!
\brief  Invalidate and enable the instruction cache.
*/
void BootICacheEnable(void);

/*!
\brief  Point VTOR at the application, load its stack pointer and jump.

\details
  The application inherits every peripheral left configured by the
  bootloader.

\param  vtor  Application vector table address.
\param  sp    Initial stack pointer.
\param  pc    Reset handler address.
*/
void __attribute__((noreturn)) BootJump(uint32_t vtor, uint32_t sp, uint32_t pc);

#endif
