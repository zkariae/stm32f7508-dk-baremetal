#include <stdint.h>

/* ------------------------------------------------------------------ */
/* RCC                                                                 */
/* ------------------------------------------------------------------ */
#define RCC_BASE        0x40023800UL
#define RCC_CR          (*(volatile uint32_t *)(RCC_BASE + 0x00))
#define RCC_PLLCFGR     (*(volatile uint32_t *)(RCC_BASE + 0x04))
#define RCC_CFGR        (*(volatile uint32_t *)(RCC_BASE + 0x08))
#define RCC_AHB1ENR     (*(volatile uint32_t *)(RCC_BASE + 0x30))
#define RCC_APB1ENR     (*(volatile uint32_t *)(RCC_BASE + 0x40))
#define RCC_APB2ENR     (*(volatile uint32_t *)(RCC_BASE + 0x44))

#define RCC_CR_HSEON    (1U << 16)
#define RCC_CR_HSERDY   (1U << 17)
#define RCC_CR_PLLON    (1U << 24)
#define RCC_CR_PLLRDY   (1U << 25)

#define RCC_APB1ENR_PWREN    (1U << 28)
#define RCC_APB2ENR_USART1EN (1U << 4)
#define RCC_AHB1ENR_GPIOAEN  (1U << 0)
#define RCC_AHB1ENR_GPIOIEN  (1U << 8)

/* ------------------------------------------------------------------ */
/* PWR                                                                 */
/* ------------------------------------------------------------------ */
#define PWR_BASE        0x40007000UL
#define PWR_CR1         (*(volatile uint32_t *)(PWR_BASE + 0x00))
#define PWR_CSR1        (*(volatile uint32_t *)(PWR_BASE + 0x04))

#define PWR_CR1_VOS      (3U << 14)
#define PWR_CR1_ODEN     (1U << 16)
#define PWR_CR1_ODSWEN   (1U << 17)
#define PWR_CSR1_ODRDY   (1U << 16)
#define PWR_CSR1_ODSWRDY (1U << 17)

/* ------------------------------------------------------------------ */
/* FLASH                                                               */
/* ------------------------------------------------------------------ */
#define FLASH_R_BASE    0x40023C00UL
#define FLASH_ACR       (*(volatile uint32_t *)(FLASH_R_BASE + 0x00))

#define FLASH_ACR_LATENCY_7WS  (7U << 0)
#define FLASH_ACR_PRFTEN       (1U << 8)
#define FLASH_ACR_ARTEN        (1U << 9)

/* ------------------------------------------------------------------ */
/* SysTick                                                             */
/* ------------------------------------------------------------------ */
#define SYSTICK_BASE    0xE000E010UL
#define SYST_CSR        (*(volatile uint32_t *)(SYSTICK_BASE + 0x00))
#define SYST_RVR        (*(volatile uint32_t *)(SYSTICK_BASE + 0x04))
#define SYST_CVR        (*(volatile uint32_t *)(SYSTICK_BASE + 0x08))

#define SYST_CSR_ENABLE    (1U << 0)
#define SYST_CSR_TICKINT   (1U << 1)
#define SYST_CSR_CLKSOURCE (1U << 2)

/* ------------------------------------------------------------------ */
/* GPIO                                                                */
/* ------------------------------------------------------------------ */
#define GPIOA_BASE      0x40020000UL
#define GPIOA_MODER     (*(volatile uint32_t *)(GPIOA_BASE + 0x00))
#define GPIOA_OSPEEDR   (*(volatile uint32_t *)(GPIOA_BASE + 0x08))
#define GPIOA_AFRH      (*(volatile uint32_t *)(GPIOA_BASE + 0x24))

#define GPIOI_BASE      0x40022000UL
#define GPIOI_MODER     (*(volatile uint32_t *)(GPIOI_BASE + 0x00))
#define GPIOI_BSRR      (*(volatile uint32_t *)(GPIOI_BASE + 0x18))

#define LED             1       /* PI1, LD1 green */
#define TX_PIN          9       /* PA9, VCP_TX    */

/* ------------------------------------------------------------------ */
/* USART1 — RM0385 section 31, register map table 174                  */
/* Note the F7 names: ISR and TDR, not the SR and DR of the F4.        */
/* ------------------------------------------------------------------ */
#define USART1_BASE     0x40011000UL
#define USART1_CR1      (*(volatile uint32_t *)(USART1_BASE + 0x00))
#define USART1_BRR      (*(volatile uint32_t *)(USART1_BASE + 0x0C))
#define USART1_ISR      (*(volatile uint32_t *)(USART1_BASE + 0x1C))
#define USART1_TDR      (*(volatile uint32_t *)(USART1_BASE + 0x28))

#define USART_CR1_UE    (1U << 0)
#define USART_CR1_TE    (1U << 3)
#define USART_ISR_TC    (1U << 6)
#define USART_ISR_TXE   (1U << 7)

/* ------------------------------------------------------------------ */
/* Clock plan: HSE 25 MHz -> 216 MHz SYSCLK, APB2 at 108 MHz           */
/* ------------------------------------------------------------------ */
#define PLL_M   25U
#define PLL_N   432U
#define PLL_P   0U
#define PLL_Q   9U

#define SYSCLK_HZ   216000000UL
#define APB2_HZ     108000000UL
#define BAUDRATE    115200UL

static volatile uint32_t g_ticks;

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
    RCC_CR |= RCC_CR_HSEON;
    while (!(RCC_CR & RCC_CR_HSERDY)) { }

    RCC_APB1ENR |= RCC_APB1ENR_PWREN;
    (void)RCC_APB1ENR;

    PWR_CR1 |= PWR_CR1_VOS;

    RCC_PLLCFGR = (PLL_M << 0)
                | (PLL_N << 6)
                | (PLL_P << 16)
                | (1U    << 22)
                | (PLL_Q << 24);

    RCC_CR |= RCC_CR_PLLON;

    PWR_CR1 |= PWR_CR1_ODEN;
    while (!(PWR_CSR1 & PWR_CSR1_ODRDY)) { }

    PWR_CR1 |= PWR_CR1_ODSWEN;
    while (!(PWR_CSR1 & PWR_CSR1_ODSWRDY)) { }

    FLASH_ACR = FLASH_ACR_LATENCY_7WS | FLASH_ACR_PRFTEN | FLASH_ACR_ARTEN;
    while ((FLASH_ACR & 0xFU) != FLASH_ACR_LATENCY_7WS) { }

    RCC_CFGR = (0U << 4)        /* HPRE  /1 -> 216 MHz */
             | (5U << 10)       /* PPRE1 /4 ->  54 MHz */
             | (4U << 13);      /* PPRE2 /2 -> 108 MHz */

    while (!(RCC_CR & RCC_CR_PLLRDY)) { }

    RCC_CFGR |= (2U << 0);
    while (((RCC_CFGR >> 2) & 3U) != 2U) { }
}

static void systick_init(void)
{
    SYST_RVR = (SYSCLK_HZ / 1000U) - 1U;
    SYST_CVR = 0;
    SYST_CSR = SYST_CSR_CLKSOURCE | SYST_CSR_TICKINT | SYST_CSR_ENABLE;
}

static void uart_init(void)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOAEN;
    RCC_APB2ENR |= RCC_APB2ENR_USART1EN;
    (void)RCC_APB2ENR;

    /* PA9 to alternate function mode: MODER bits [19:18] = 10 */
    GPIOA_MODER &= ~(3U << (TX_PIN * 2));
    GPIOA_MODER |=  (2U << (TX_PIN * 2));

    /* High speed, so the edges stay clean at 115200 and above */
    GPIOA_OSPEEDR |= (3U << (TX_PIN * 2));

    /* AF7 = USART1_TX. Pins 8..15 live in AFRH, four bits each,
     * so pin 9 occupies bits [7:4].                                   */
    GPIOA_AFRH &= ~(0xFU << ((TX_PIN - 8) * 4));
    GPIOA_AFRH |=  (7U   << ((TX_PIN - 8) * 4));

    /* 108 MHz / 115200 = 937.5 -> 937 gives 115261 baud, 0.05 % off */
    USART1_BRR = APB2_HZ / BAUDRATE;

    /* 8N1 is the reset state, so only enable transmitter and USART */
    USART1_CR1 = USART_CR1_TE | USART_CR1_UE;
}

static void uart_putc(char c)
{
    while (!(USART1_ISR & USART_ISR_TXE)) { }
    USART1_TDR = (uint32_t)c;
}

static void uart_puts(const char *s)
{
    while (*s) {
        if (*s == '\n') {
            uart_putc('\r');    /* terminals expect CRLF */
        }
        uart_putc(*s++);
    }
}

/* Print an unsigned value in hexadecimal, always eight digits */
static void uart_hex32(uint32_t v)
{
    static const char digits[] = "0123456789ABCDEF";
    uart_puts("0x");
    for (int shift = 28; shift >= 0; shift -= 4) {
        uart_putc(digits[(v >> shift) & 0xFU]);
    }
}

/* Print an unsigned decimal value */
static void uart_dec(uint32_t v)
{
    char buf[11];
    int i = 0;

    if (v == 0) {
        uart_putc('0');
        return;
    }
    while (v > 0) {
        buf[i++] = (char)('0' + (v % 10U));
        v /= 10U;
    }
    while (i > 0) {
        uart_putc(buf[--i]);
    }
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
    uart_init();
    led_init();

    uart_puts("\n");
    uart_puts("STM32F750N8 — bare metal, no HAL\n");
    uart_puts("--------------------------------\n");

    uart_puts("SYSCLK   : ");
    uart_dec(SYSCLK_HZ / 1000000U);
    uart_puts(" MHz\n");

    uart_puts("APB2     : ");
    uart_dec(APB2_HZ / 1000000U);
    uart_puts(" MHz\n");

    uart_puts("Baudrate : ");
    uart_dec(BAUDRATE);
    uart_puts("\n\n");

    /* Read the registers back from the chip rather than trusting what
     * we wrote — this is the whole point of having a UART.            */
    uart_puts("RCC_CFGR   = ");
    uart_hex32(RCC_CFGR);
    uart_puts("\n");

    uart_puts("RCC_PLLCFGR= ");
    uart_hex32(RCC_PLLCFGR);
    uart_puts("\n");

    uart_puts("FLASH_ACR  = ");
    uart_hex32(FLASH_ACR);
    uart_puts("\n");

    uart_puts("PWR_CSR1   = ");
    uart_hex32(PWR_CSR1);
    uart_puts("\n\n");

    uint32_t seconds = 0;
    while (1) {
        GPIOI_BSRR = (1U << LED);
        delay_ms(500);
        GPIOI_BSRR = (1U << (LED + 16));
        delay_ms(500);

        uart_puts("uptime ");
        uart_dec(++seconds);
        uart_puts(" s\n");
    }
}
