// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/startup.c
\brief      Reset handler, vector table and default exception handlers.

\author     Z. BEN-AKKA
\version    1.2
\date       10/10/2026

\details
  Shared by every application. On reset:
  1) Leaves for the ST ROM bootloader (USB DFU) if USER is held.
  2) Copies .data from flash to RAM and zeroes .bss.
  3) Calls main().
  Exception handlers are weak aliases of Default_Handler, which traps.

\section startup_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 29/08/2026 | Z. BEN-AKKA | Initial version.                             |
| 1.1     | 25/09/2026 | Z. BEN-AKKA | Enter the ROM bootloader when USER is held.  |
| 1.2     | 10/10/2026 | Z. BEN-AKKA | Use defines.h; comments per Contributing.md. |
****************************
*/

#include <stdint.h>

#include "defines.h"

// Provided by the linker script
extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;

int main(void);

/*!
\brief  Jump to the ST ROM bootloader if USER is pressed at reset.

\details
  Runs before anything else so the ROM finds the chip in reset state; the
  only clock gate opened is closed again. Also turns the ROM's exit jump
  (PLL running, VTOR on the ROM) into a real system reset.
*/
static void enter_bootloader_if_requested(void)
{
  // After a reset the core always runs on HSI: anything else is the ROM jumping back
  if (RCC_CFGR & RCC_CFGR_SWS_MASK) {
    __asm volatile("dsb");
    SCB_AIRCR = SCB_AIRCR_VECTKEY | SCB_AIRCR_SYSRESETREQ;
    while (1) {}
  }

  RCC_AHB1ENR |= RCC_AHB1ENR_GPIOIEN;
  (void)RCC_AHB1ENR; // read back: the clock reaches the port
  uint32_t pressed = GPIO_IDR(GPIOI_BASE) & (1U << USER_BUTTON_PIN);
  RCC_AHB1ENR &= ~RCC_AHB1ENR_GPIOIEN;

  if (!pressed) {
    return;
  }

  uint32_t sp = REG(SYSMEM_BASE);
  uint32_t pc = REG(SYSMEM_BASE + 4);
  SCB_VTOR = SYSMEM_BASE;
  __asm volatile("msr msp, %0\n\tbx %1" : : "r"(sp), "r"(pc));
  __builtin_unreachable();
}

/*!
\brief  Entry point after reset: initialise memory, then run main().
*/
void Reset_Handler(void)
{
  enter_bootloader_if_requested();

  // Copy .data from flash into RAM
  uint32_t *src = &_sidata;
  uint32_t *dst = &_sdata;
  while (dst < &_edata) {
    *dst++ = *src++;
  }

  // Zero .bss
  dst = &_sbss;
  while (dst < &_ebss) {
    *dst++ = 0;
  }

  main();

  while (1) {} // main must never return
}

/*!
\brief  Trap for every exception without its own handler.
*/
void Default_Handler(void)
{
  while (1) {}
}

// Weak aliases: an application defining one of these overrides it
void NMI_Handler(void) __attribute__((weak, alias("Default_Handler")));
void HardFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void MemManage_Handler(void) __attribute__((weak, alias("Default_Handler")));
void BusFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void UsageFault_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SVC_Handler(void) __attribute__((weak, alias("Default_Handler")));
void DebugMon_Handler(void) __attribute__((weak, alias("Default_Handler")));
void PendSV_Handler(void) __attribute__((weak, alias("Default_Handler")));
void SysTick_Handler(void) __attribute__((weak, alias("Default_Handler")));

/// Cortex-M vector table, placed first in flash by the linker script.
__attribute__((section(".isr_vector"), used)) void (*const vector_table[])(void) = {
    (void (*)(void))&_estack, // 0x00: initial stack pointer
    Reset_Handler,            // 0x04: reset
    NMI_Handler,
    HardFault_Handler,
    MemManage_Handler,
    BusFault_Handler,
    UsageFault_Handler,
    0, // reserved
    0, // reserved
    0, // reserved
    0, // reserved
    SVC_Handler,
    DebugMon_Handler,
    0, // reserved
    PendSV_Handler,
    SysTick_Handler,
};
