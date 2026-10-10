/* SPDX-License-Identifier: MIT */
/*!
****************************
\file       linker/internal-flash.ld
\brief      Linker script for images in the internal flash.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  STM32F750N8: 64 KB flash at 0x08000000, 320 KB contiguous RAM at
  0x20000000 (DTCM 64 KB + SRAM1 240 KB + SRAM2 16 KB). Stack at top of RAM.

\section internal_flash_ld_version_history Version history
| Version | Date       | Author      | Description                                              |
|:-------:|:----------:|:------------|:---------------------------------------------------------|
| 1.0     | 29/08/2026 | Z. BEN-AKKA | Initial version.                                         |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Moved from common/linker.ld; header per Contributing.md. |
****************************
*/

ENTRY(Reset_Handler)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 64K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 320K
}

_estack = ORIGIN(RAM) + LENGTH(RAM);   /* stack grows downward */

SECTIONS
{
    .isr_vector :
    {
        KEEP(*(.isr_vector))           /* must be first, at 0x08000000 */
    } > FLASH

    .text :
    {
        *(.text*)
        *(.rodata*)
    } > FLASH

    /* Initialised data: stored in flash, addressed in RAM */
    _sidata = LOADADDR(.data);
    .data :
    {
        _sdata = .;
        *(.data*)
        _edata = .;
    } > RAM AT > FLASH

    .bss :
    {
        _sbss = .;
        *(.bss*)
        *(COMMON)
        _ebss = .;
    } > RAM
}
