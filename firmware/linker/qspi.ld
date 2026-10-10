/* SPDX-License-Identifier: MIT */
/*!
****************************
\file       linker/qspi.ld
\brief      Linker script for images run in place from the QSPI flash.

\author     Z. BEN-AKKA
\version    1.1
\date       10/10/2026

\details
  Code at 0x90000000 (N25Q128A, 16 MB, memory-mapped by a bootloader such
  as 08-custombootloader). RAM as in internal-flash.ld.

\section qspi_ld_version_history Version history
| Version | Date       | Author      | Description                 |
|:-------:|:----------:|:------------|:----------------------------|
| 1.0     | 08/10/2026 | Z. BEN-AKKA | Initial version.            |
| 1.1     | 10/10/2026 | Z. BEN-AKKA | Header per Contributing.md. |
****************************
*/

ENTRY(Reset_Handler)

MEMORY
{
    QSPI  (rx)  : ORIGIN = 0x90000000, LENGTH = 16M
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 320K
}

_estack = ORIGIN(RAM) + LENGTH(RAM);   /* stack grows downward */

SECTIONS
{
    .isr_vector :
    {
        KEEP(*(.isr_vector))           /* must be first: the bootloader reads SP and PC here */
    } > QSPI

    .text :
    {
        *(.text*)
        *(.rodata*)
    } > QSPI

    /* Initialised data: stored in QSPI, addressed in RAM */
    _sidata = LOADADDR(.data);
    .data :
    {
        _sdata = .;
        *(.data*)
        _edata = .;
    } > RAM AT > QSPI

    .bss :
    {
        _sbss = .;
        *(.bss*)
        *(COMMON)
        _ebss = .;
    } > RAM
}
