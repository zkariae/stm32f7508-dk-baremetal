/* STM32F750N8H6 — 64K flash, 320K contiguous RAM
 * DTCM 64K @ 0x20000000 + SRAM1 240K + SRAM2 16K, up to 0x20050000
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
