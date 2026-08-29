#include <stdint.h>

/* ------------------------------------------------------------------ */
/* RCC — Reset and Clock Control, RM0385 section 5                     */
/* ------------------------------------------------------------------ */
#define RCC_BASE        0x40023800UL
#define RCC_CR          (*(volatile uint32_t *)(RCC_BASE + 0x00))
#define RCC_PLLCFGR     (*(volatile uint32_t *)(RCC_BASE + 0x04))
#define RCC_CFGR        (*(volatile uint32_t *)(RCC_BASE + 0x08))
#define RCC_AHB1ENR     (*(volatile uint32_t *)(RCC_BASE + 0x30))
#define RCC_APB1ENR     (*(volatile uint32_t *)(RCC_BASE + 0x40))

#define RCC_CR_HSEON    (1U << 16)
#define RCC_CR_HSERDY   (1U << 17)
#define RCC_CR_PLLON    (1U << 24)
#define RCC_CR_PLLRDY   (1U << 25)

#define RCC_APB1ENR_PWREN  (1U << 28)
#define RCC_AHB1ENR_GPIOIEN (1U << 8)

/* ------------------------------------------------------------------ */
/* PWR — Power control, RM0385 section 4                               */
/* ------------------------------------------------------------------ */
#define PWR_BASE        0x40007000UL
#define PWR_CR1         (*(volatile uint32_t *)(PWR_BASE + 0x00))
#define PWR_CSR1        (*(volatile uint32_t *)(PWR_BASE + 0x04))

#define PWR_CR1_VOS     (3U << 14)      /* 11 = Scale 1 */
#define PWR_CR1_ODEN    (1U << 16)
#define PWR_CR1_ODSWEN  (1U << 17)
#define PWR_CSR1_ODRDY  (1U << 16)
#define PWR_CSR1_ODSWRDY (1U << 17)

/* ------------------------------------------------------------------ */
/* FLASH — RM0385 section 3                                            */
/* ------------------------------------------------------------------ */
#define FLASH_BASE_R    0x40023C00UL
#define FLASH_ACR       (*(volatile uint32_t *)(FLASH_BASE_R + 0x00))

#define FLASH_ACR_LATENCY_7WS  (7U << 0)   /* 210 < HCLK <= 216 MHz at 3.3 V */
#define FLASH_ACR_PRFTEN       (1U << 8)
#define FLASH_ACR_ARTEN        (1U << 9)

/* ------------------------------------------------------------------ */
/* SysTick — inside the Cortex-M7 core, not a peripheral               */
/* ------------------------------------------------------------------ */
#define SYSTICK_BASE    0xE000E010UL
#define SYST_CSR        (*(volatile uint32_t *)(SYSTICK_BASE + 0x00))
#define SYST_RVR        (*(volatile uint32_t *)(SYSTICK_BASE + 0x04))
#define SYST_CVR        (*(volatile uint32_t *)(SYSTICK_BASE + 0x08))

#define SYST_CSR_ENABLE     (1U << 0)
#define SYST_CSR_TICKINT    (1U << 1)
#define SYST_CSR_CLKSOURCE  (1U << 2)   /* 1 = processor clock */

/* ------------------------------------------------------------------ */
/* GPIOI — LD1 green on PI1, active high                               */
/* ------------------------------------------------------------------ */
#define GPIOI_BASE      0x40022000UL
#define GPIOI_MODER     (*(volatile uint32_t *)(GPIOI_BASE + 0x00))
#define GPIOI_BSRR      (*(volatile uint32_t *)(GPIOI_BASE + 0x18))

#define LED             1

/* ------------------------------------------------------------------ */
/* Clock plan                                                          */
/*                                                                     */
/*   HSE 25 MHz  ->  /M=25  ->  2 MHz VCO input                        */
/*               ->  xN=432 ->  432 MHz VCO                            */
/*               ->  /P=2   ->  216 MHz SYSCLK                         */
/*                                                                     */
/*   AHB  /1 -> 216 MHz                                                */
/*   APB1 /4 ->  54 MHz                                                */
/*   APB2 /2 -> 108 MHz                                                */
/* ------------------------------------------------------------------ */
#define PLL_M   25U
#define PLL_N   432U
#define PLL_P   0U      /* 00 = divide by 2 */
#define PLL_Q   9U      /* 432 / 9 = 48 MHz for USB */

#define SYSCLK_HZ  216000000UL

static volatile uint32_t g_ticks;   /* milliseconds since boot */

void SysTick_Handler(void)
{
    g_ticks++;
}

static void delay_ms(uint32_t ms)
{
    uint32_t start = g_ticks;
    while ((g_ticks - start) < ms) {
        __asm__("nop");
    }
}

static void clock_init(void)
{
    /* 1. Start the external 25 MHz crystal and wait for it to stabilise */
    RCC_CR |= RCC_CR_HSEON;
    while (!(RCC_CR & RCC_CR_HSERDY)) { }

    /* 2. The PWR block lives on APB1 — it needs a clock before we can
     *    write to it. Same trap as the GPIO in the blink project.      */
    RCC_APB1ENR |= RCC_APB1ENR_PWREN;
    (void)RCC_APB1ENR;                  /* let the write land */

    /* 3. Voltage scale 1. On its own this caps HCLK at 180 MHz;
     *    over-drive below lifts it to 216 MHz.                         */
    PWR_CR1 |= PWR_CR1_VOS;

    /* 4. Configure the PLL while it is still stopped, then start it.
     *    PLLCFGR can only be written when PLLON is clear.              */
    RCC_PLLCFGR = (PLL_M << 0)
                | (PLL_N << 6)
                | (PLL_P << 16)
                | (1U    << 22)         /* PLLSRC = HSE */
                | (PLL_Q << 24);

    RCC_CR |= RCC_CR_PLLON;

    /* 5. Over-drive, in the order the reference manual demands.
     *    ODSWEN may only be set once ODRDY is up.                      */
    PWR_CR1 |= PWR_CR1_ODEN;
    while (!(PWR_CSR1 & PWR_CSR1_ODRDY)) { }

    PWR_CR1 |= PWR_CR1_ODSWEN;
    while (!(PWR_CSR1 & PWR_CSR1_ODSWRDY)) { }

    /* 6. Flash wait states BEFORE the switch. At 216 MHz and 3.3 V the
     *    flash needs 7 wait states — switch first and the core fetches
     *    garbage and dies with no diagnostic.                          */
    FLASH_ACR = FLASH_ACR_LATENCY_7WS | FLASH_ACR_PRFTEN | FLASH_ACR_ARTEN;
    while ((FLASH_ACR & 0xFU) != FLASH_ACR_LATENCY_7WS) { }

    /* 7. Bus prescalers, also before the switch, so no bus ever sees
     *    216 MHz. APB1 max 54 MHz, APB2 max 108 MHz.                   */
    RCC_CFGR = (0U << 4)        /* HPRE  = /1  -> 216 MHz */
             | (5U << 10)       /* PPRE1 = /4  ->  54 MHz */
             | (4U << 13);      /* PPRE2 = /2  -> 108 MHz */

    /* 8. Wait for the PLL to lock, then switch the system to it */
    while (!(RCC_CR & RCC_CR_PLLRDY)) { }

    RCC_CFGR |= (2U << 0);              /* SW = 10, PLL as system clock */
    while (((RCC_CFGR >> 2) & 3U) != 2U) { }   /* SWS confirms */
}

static void systick_init(void)
{
    SYST_RVR = (SYSCLK_HZ / 1000U) - 1U;   /* one interrupt per millisecond */
    SYST_CVR = 0;
    SYST_CSR = SYST_CSR_CLKSOURCE | SYST_CSR_TICKINT | SYST_CSR_ENABLE;
}

static void led_init(void)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOIEN;
    (void)RCC_AHB1ENR;

    GPIOI_MODER &= ~(3U << (LED * 2));
    GPIOI_MODER |=  (1U << (LED * 2));
}

int main(void)
{
    clock_init();
    systick_init();
    led_init();

    /* A one-second heartbeat. If the clock plan is wrong, this beats at
     * the wrong rate — which is exactly how you check it without a scope.
     * At 16 MHz HSI it would run 13.5 times slower.                     */
    while (1) {
        GPIOI_BSRR = (1U << LED);          /* on  */
        delay_ms(500);
        GPIOI_BSRR = (1U << (LED + 16));   /* off */
        delay_ms(500);
    }
}
