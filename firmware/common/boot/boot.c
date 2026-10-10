// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/boot/boot.c
\brief      Hand-over from a bootloader to an application image.

\author     Z. BEN-AKKA
\version    1.0
\date       10/10/2026

\details
  API documented in boot.h.

\section boot_c_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#include "boot/boot.h"

#include <stdint.h>

#include "defines.h"

int BootAppLooksValid(uint32_t sp, uint32_t pc, uint32_t base, uint32_t size)
{
  int sp_ok = sp > RAM_BASE && sp <= RAM_END && (sp & 3) == 0;
  int pc_ok = pc > base && pc < base + size && (pc & 1); // Thumb bit

  return sp_ok && pc_ok;
}

void BootICacheEnable(void)
{
  __asm volatile("dsb\n\tisb");
  SCB_ICIALLU = 0; // contents are random after reset
  __asm volatile("dsb\n\tisb");
  SCB_CCR |= SCB_CCR_IC;
  __asm volatile("dsb\n\tisb");
}

void BootJump(uint32_t vtor, uint32_t sp, uint32_t pc)
{
  SCB_VTOR = vtor;
  __asm volatile("dsb\n\tisb");
  __asm volatile("msr msp, %0\n\tbx %1" : : "r"(sp), "r"(pc));
  __builtin_unreachable();
}
