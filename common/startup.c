#include <stdint.h>

/* Symbols provided by the linker script */
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;

int main(void);

void Reset_Handler(void)
{
    /* Copy .data from flash into RAM */
    uint32_t *src = &_sidata;
    uint32_t *dst = &_sdata;
    while (dst < &_edata) {
        *dst++ = *src++;
    }

    /* Zero .bss */
    dst = &_sbss;
    while (dst < &_ebss) {
        *dst++ = 0;
    }

    main();

    while (1) { }   /* main must never return */
}

void Default_Handler(void)
{
    while (1) { }
}

/* Weak aliases: define any of these elsewhere and yours wins */
void NMI_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void MemManage_Handler(void)  __attribute__((weak, alias("Default_Handler")));
void BusFault_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void UsageFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void)        __attribute__((weak, alias("Default_Handler")));
void DebugMon_Handler(void)   __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void)     __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void)    __attribute__((weak, alias("Default_Handler")));

/* Vector table, forced into its own section at 0x08000000 */
__attribute__((section(".isr_vector"), used))
void (* const vector_table[])(void) = {
    (void (*)(void)) &_estack,   /* 0x00: initial stack pointer */
    Reset_Handler,               /* 0x04: reset                 */
    NMI_Handler,
    HardFault_Handler,
    MemManage_Handler,
    BusFault_Handler,
    UsageFault_Handler,
    0, 0, 0, 0,                  /* reserved */
    SVC_Handler,
    DebugMon_Handler,
    0,                           /* reserved */
    PendSV_Handler,
    SysTick_Handler,
};