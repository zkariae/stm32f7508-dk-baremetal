// SPDX-License-Identifier: MIT
/*!
****************************
\file       defines.h
\brief      STM32F750N8 registers and STM32F7508-DK board definitions.

\author     Z. BEN-AKKA
\version    1.0
\date       10/10/2026

\details
  Single definition point for the peripheral registers, bit fields and board
  wiring used by the firmware. Addresses and offsets follow RM0385.
  - Registers are lvalues: RCC_CR |= RCC_CR_HSEON;
  - GPIO macros take a port base address: GPIO_MODER(GPIOI_BASE).
  - Multi-bit fields take their value: QSPI_CR_PRESCALER(1).
  Application choices (clock plan, baud rate, buffers) stay in each application.

\section defines_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef DEFINES_H
#define DEFINES_H

#include <stdint.h>

/* Return codes (Contributing.md, part B.11) */
#define SUCCESS 0x00 ///< Operation completed.
#define FAILURE 0x01 ///< Generic failure.
#define TIMEOUT 0x02 ///< Hardware did not respond in time.

/// Memory-mapped 32-bit register at a fixed address.
#define REG(addr) (*(volatile uint32_t *)(addr))

/* Memory map - RM0385 section 2.2 */
#define FLASH_MEM_BASE 0x08000000UL ///< Internal flash, 64 KB.
#define SYSMEM_BASE    0x1FF00000UL ///< ST ROM bootloader (AN2606).
#define RAM_BASE       0x20000000UL ///< DTCM 64 KB + SRAM1 240 KB + SRAM2 16 KB.
#define RAM_END        0x20050000UL ///< First address past the RAM.
#define QSPI_MEM_BASE  0x90000000UL ///< QUADSPI memory-mapped window.

/* Board - STM32F7508-DK (UM2470, MB1191 schematic) */
#define HSE_HZ 25000000UL ///< External crystal.
#define HSI_HZ 16000000UL ///< Internal oscillator, clock source at reset.

#define LED_PIN         1  ///< PI1, LD1 green, active high.
#define USER_BUTTON_PIN 11 ///< PI11, B1 blue, high when pressed.
#define VCP_TX_PIN      9  ///< PA9, USART1_TX to the ST-LINK virtual COM port.
#define LCD_DISP_PIN    12 ///< PI12, LCD_DISP: panel enable.
#define LCD_BL_PIN      3  ///< PK3, LCD_BL_CTRL: backlight enable.

/* Panel - RK043FN48H, 480x272. Back porches include the sync pulse:
 * 1 + 42 + 480 + 8 = 531 clocks per line, 10 + 2 + 272 + 4 = 288 lines. */
#define LCD_WIDTH  480U
#define LCD_HEIGHT 272U
#define LCD_HSW    1U  ///< Horizontal sync width, pixel clocks.
#define LCD_HBP    42U ///< Horizontal back porch.
#define LCD_HFP    8U  ///< Horizontal front porch.
#define LCD_VSW    10U ///< Vertical sync width, lines.
#define LCD_VBP    2U  ///< Vertical back porch.
#define LCD_VFP    4U  ///< Vertical front porch.

/* QSPI flash - Micron N25Q128A, 16 MB */
#define N25Q_CMD_QUAD_OUT_READ 0x6B       ///< 1-1-4: instruction and address on 1 line, data on 4.
#define N25Q_QUAD_OUT_DUMMY    8          ///< Power-on default dummy cycles for 0x6B.
#define N25Q128A_SIZE_LOG2     24         ///< 2^24 bytes = 16 MB.
#define N25Q128A_ID            0x18BA20UL ///< Manufacturer 0x20, type 0xBA, 128 Mbit; LSB first.

/* RCC - RM0385 section 5 */
#define RCC_BASE       0x40023800UL
#define RCC_CR         REG(RCC_BASE + 0x00)
#define RCC_PLLCFGR    REG(RCC_BASE + 0x04)
#define RCC_CFGR       REG(RCC_BASE + 0x08)
#define RCC_AHB1ENR    REG(RCC_BASE + 0x30)
#define RCC_AHB3ENR    REG(RCC_BASE + 0x38)
#define RCC_APB1ENR    REG(RCC_BASE + 0x40)
#define RCC_APB2ENR    REG(RCC_BASE + 0x44)
#define RCC_PLLSAICFGR REG(RCC_BASE + 0x88)
#define RCC_DCKCFGR1   REG(RCC_BASE + 0x8C)

#define RCC_CR_HSEON     (1U << 16)
#define RCC_CR_HSERDY    (1U << 17)
#define RCC_CR_PLLON     (1U << 24)
#define RCC_CR_PLLRDY    (1U << 25)
#define RCC_CR_PLLSAION  (1U << 28)
#define RCC_CR_PLLSAIRDY (1U << 29)

#define RCC_CFGR_SW_MASK  (3U << 0)
#define RCC_CFGR_SWS_MASK (3U << 2) ///< 00 = HSI, the reset value.

/// GPIO clock enables: port A is bit 0, up to port K at bit 10.
#define RCC_AHB1ENR_GPIOAEN  (1U << 0)
#define RCC_AHB1ENR_GPIOBEN  (1U << 1)
#define RCC_AHB1ENR_GPIOCEN  (1U << 2)
#define RCC_AHB1ENR_GPIODEN  (1U << 3)
#define RCC_AHB1ENR_GPIOEEN  (1U << 4)
#define RCC_AHB1ENR_GPIOFEN  (1U << 5)
#define RCC_AHB1ENR_GPIOGEN  (1U << 6)
#define RCC_AHB1ENR_GPIOHEN  (1U << 7)
#define RCC_AHB1ENR_GPIOIEN  (1U << 8)
#define RCC_AHB1ENR_GPIOJEN  (1U << 9)
#define RCC_AHB1ENR_GPIOKEN  (1U << 10)
#define RCC_AHB3ENR_QSPIEN   (1U << 1)
#define RCC_APB1ENR_PWREN    (1U << 28)
#define RCC_APB2ENR_USART1EN (1U << 4)
#define RCC_APB2ENR_LTDCEN   (1U << 26)

/* PWR - RM0385 section 4 */
#define PWR_BASE 0x40007000UL
#define PWR_CR1  REG(PWR_BASE + 0x00)
#define PWR_CSR1 REG(PWR_BASE + 0x04)

#define PWR_CR1_VOS      (3U << 14) ///< 11 = voltage scale 1.
#define PWR_CR1_ODEN     (1U << 16)
#define PWR_CR1_ODSWEN   (1U << 17)
#define PWR_CSR1_ODRDY   (1U << 16)
#define PWR_CSR1_ODSWRDY (1U << 17)

/* FLASH interface - RM0385 section 3 */
#define FLASH_R_BASE 0x40023C00UL
#define FLASH_ACR    REG(FLASH_R_BASE + 0x00)

#define FLASH_ACR_LATENCY(ws)  ((uint32_t)(ws) << 0) ///< Wait states; 7 for 216 MHz at 3.3 V.
#define FLASH_ACR_LATENCY_MASK (0xFU << 0)
#define FLASH_ACR_PRFTEN       (1U << 8)
#define FLASH_ACR_ARTEN        (1U << 9)

/* GPIO - RM0385 section 6. Ports are 0x400 apart from 0x40020000. */
#define GPIOA_BASE 0x40020000UL
#define GPIOB_BASE 0x40020400UL
#define GPIOC_BASE 0x40020800UL
#define GPIOD_BASE 0x40020C00UL
#define GPIOE_BASE 0x40021000UL
#define GPIOF_BASE 0x40021400UL
#define GPIOG_BASE 0x40021800UL
#define GPIOH_BASE 0x40021C00UL
#define GPIOI_BASE 0x40022000UL
#define GPIOJ_BASE 0x40022400UL
#define GPIOK_BASE 0x40022800UL

/// Port base address from a port index, for tables storing ports as one byte.
#define GPIO_PORT(n) (GPIOA_BASE + (n) * 0x400UL)
#define PORT_A       0
#define PORT_B       1
#define PORT_C       2
#define PORT_D       3
#define PORT_E       4
#define PORT_F       5
#define PORT_G       6
#define PORT_H       7
#define PORT_I       8
#define PORT_J       9
#define PORT_K       10

#define GPIO_MODER(p)   REG((p) + 0x00)
#define GPIO_OTYPER(p)  REG((p) + 0x04)
#define GPIO_OSPEEDR(p) REG((p) + 0x08)
#define GPIO_PUPDR(p)   REG((p) + 0x0C)
#define GPIO_IDR(p)     REG((p) + 0x10)
#define GPIO_ODR(p)     REG((p) + 0x14)
#define GPIO_BSRR(p)    REG((p) + 0x18) ///< Atomic set (bits 0-15) / reset (bits 16-31).
#define GPIO_AFRL(p)    REG((p) + 0x20)
#define GPIO_AFRH(p)    REG((p) + 0x24)
#define GPIO_AFR(p, n)  REG((p) + 0x20 + ((n) / 8) * 4) ///< AFRL or AFRH for pin n.

/// MODER field values, two bits per pin.
#define GPIO_MODE_INPUT  0U
#define GPIO_MODE_OUTPUT 1U
#define GPIO_MODE_AF     2U
#define GPIO_MODE_ANALOG 3U

/* USART - RM0385 section 31 */
#define USART1_BASE 0x40011000UL

/// USART registers, from the instance base address (USARTx_BASE).
#define USART_CR1(b) REG((b) + 0x00)
#define USART_BRR(b) REG((b) + 0x0C)
#define USART_ISR(b) REG((b) + 0x1C)
#define USART_RDR(b) REG((b) + 0x24)
#define USART_TDR(b) REG((b) + 0x28)

#define USART_CR1_UE   (1U << 0)
#define USART_CR1_RE   (1U << 2)
#define USART_CR1_TE   (1U << 3)
#define USART_ISR_RXNE (1U << 5)
#define USART_ISR_TC   (1U << 6)
#define USART_ISR_TXE  (1U << 7)

/* QUADSPI - RM0385 section 13 */
#define QSPI_BASE  0xA0001000UL
#define QSPI_CR    REG(QSPI_BASE + 0x00)
#define QSPI_DCR   REG(QSPI_BASE + 0x04)
#define QSPI_SR    REG(QSPI_BASE + 0x08)
#define QSPI_FCR   REG(QSPI_BASE + 0x0C)
#define QSPI_DLR   REG(QSPI_BASE + 0x10)
#define QSPI_CCR   REG(QSPI_BASE + 0x14)
#define QSPI_AR    REG(QSPI_BASE + 0x18)
#define QSPI_ABR   REG(QSPI_BASE + 0x1C)
#define QSPI_DR    REG(QSPI_BASE + 0x20)
#define QSPI_DR8   (*(volatile uint8_t *)(QSPI_BASE + 0x20)) ///< Byte access: pops one byte.
#define QSPI_PSMKR REG(QSPI_BASE + 0x24)
#define QSPI_PSMAR REG(QSPI_BASE + 0x28)
#define QSPI_PIR   REG(QSPI_BASE + 0x2C)
#define QSPI_LPTR  REG(QSPI_BASE + 0x30)

#define QSPI_CR_EN           (1U << 0)
#define QSPI_CR_ABORT        (1U << 1)
#define QSPI_CR_PRESCALER(n) ((uint32_t)(n) << 24) ///< Clock = HCLK / (n + 1).
#define QSPI_DCR_CSHT(n)     ((uint32_t)(n) << 8)  ///< CS high for at least n + 1 cycles.
#define QSPI_DCR_FSIZE(n)    ((uint32_t)(n) << 16) ///< Flash size = 2^(n + 1) bytes.
#define QSPI_SR_TEF          (1U << 0)
#define QSPI_SR_TCF          (1U << 1)
#define QSPI_SR_FTF          (1U << 2)
#define QSPI_SR_SMF          (1U << 3)
#define QSPI_SR_BUSY         (1U << 5)
#define QSPI_FCR_CTEF        (1U << 0)
#define QSPI_FCR_CTCF        (1U << 1)
#define QSPI_FCR_CSMF        (1U << 3)

/// CCR phase modes: 0 = skipped, 1 = one line, 2 = two lines, 3 = four lines.
#define QSPI_CCR_IMODE(m)    ((uint32_t)(m) << 8)  ///< Instruction phase.
#define QSPI_CCR_ADMODE(m)   ((uint32_t)(m) << 10) ///< Address phase.
#define QSPI_CCR_ADSIZE_24   (2U << 12)
#define QSPI_CCR_ADSIZE_32   (3U << 12)
#define QSPI_CCR_DCYC(n)     ((uint32_t)(n) << 18) ///< Dummy cycles.
#define QSPI_CCR_DMODE(m)    ((uint32_t)(m) << 24) ///< Data phase.
#define QSPI_CCR_FMODE_WRITE (0U << 26)            ///< Indirect write, also for bare commands.
#define QSPI_CCR_FMODE_READ  (1U << 26)            ///< Indirect read.
#define QSPI_CCR_FMODE_POLL  (2U << 26)            ///< Automatic status polling.
#define QSPI_CCR_FMODE_MMAP  (3U << 26)            ///< Memory-mapped.

/* LTDC - RM0385 section 18. Layer registers: 0x84 + 0x80 * (layer - 1). */
#define LTDC_BASE     0x40016800UL
#define LTDC_SSCR     REG(LTDC_BASE + 0x08)
#define LTDC_BPCR     REG(LTDC_BASE + 0x0C)
#define LTDC_AWCR     REG(LTDC_BASE + 0x10)
#define LTDC_TWCR     REG(LTDC_BASE + 0x14)
#define LTDC_GCR      REG(LTDC_BASE + 0x18)
#define LTDC_SRCR     REG(LTDC_BASE + 0x24)
#define LTDC_BCCR     REG(LTDC_BASE + 0x2C)
#define LTDC_ISR      REG(LTDC_BASE + 0x38)
#define LTDC_ICR      REG(LTDC_BASE + 0x3C)
#define LTDC_CDSR     REG(LTDC_BASE + 0x48)
#define LTDC_L1CR     REG(LTDC_BASE + 0x84)
#define LTDC_L1WHPCR  REG(LTDC_BASE + 0x88)
#define LTDC_L1WVPCR  REG(LTDC_BASE + 0x8C)
#define LTDC_L1PFCR   REG(LTDC_BASE + 0x94)
#define LTDC_L1CACR   REG(LTDC_BASE + 0x98)
#define LTDC_L1BFCR   REG(LTDC_BASE + 0xA0)
#define LTDC_L1CFBAR  REG(LTDC_BASE + 0xAC)
#define LTDC_L1CFBLR  REG(LTDC_BASE + 0xB0)
#define LTDC_L1CFBLNR REG(LTDC_BASE + 0xB4)

#define LTDC_GCR_LTDCEN (1U << 0)
#define LTDC_SRCR_IMR   (1U << 0)
#define LTDC_ISR_FUIF   (1U << 1)
#define LTDC_L1CR_LEN   (1U << 0)
#define LTDC_PF_RGB565  2U ///< LTDC_LxPFCR pixel format.

/* Cortex-M7 core - ARMv7-M Architecture Reference Manual */
#define SYST_CSR REG(0xE000E010UL)
#define SYST_RVR REG(0xE000E014UL)
#define SYST_CVR REG(0xE000E018UL)

#define SYST_CSR_ENABLE    (1U << 0)
#define SYST_CSR_TICKINT   (1U << 1)
#define SYST_CSR_CLKSOURCE (1U << 2) ///< 1 = processor clock.

#define SCB_VTOR    REG(0xE000ED08UL)
#define SCB_AIRCR   REG(0xE000ED0CUL)
#define SCB_CCR     REG(0xE000ED14UL)
#define SCB_ICIALLU REG(0xE000EF50UL) ///< Any write invalidates the I-cache.

#define SCB_AIRCR_VECTKEY     (0x05FAU << 16) ///< Required for any AIRCR write.
#define SCB_AIRCR_SYSRESETREQ (1U << 2)
#define SCB_CCR_DC            (1U << 16)
#define SCB_CCR_IC            (1U << 17)

#endif
