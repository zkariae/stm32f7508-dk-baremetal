/*
 * 04-lcd-backlight
 *
 * Before configuring the LTDC — thirty pins, a dedicated PLL and a dozen
 * registers — check that the panel and its backlight actually come up.
 * Two GPIOs are enough:
 *
 *   PK3  LCD_BL_CTRL  drives EN on the STLD40DPUR backlight boost
 *   PI12 LCD_DISP     enables the panel itself
 *
 * A working run turns the screen from black to an even pale grey: the
 * panel is lit and powered, but the LTDC is not driving it yet, so there
 * is no image. That grey is the result you want here.
 *
 * If this does not work, nothing built on top of it will, and you would
 * be debugging the LTDC for a problem that is not in the LTDC.
 */

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
#define RCC_AHB1ENR_GPIOKEN  (1U << 10)   /* K is the 11th port: A=0 ... K=10 */

/* ------------------------------------------------------------------ */
/* PWR / FLASH                                                         */
/* ------------------------------------------------------------------ */
#define PWR_BASE        0x40007000UL
#define PWR_CR1         (*(volatile uint32_t *)(PWR_BASE + 0x00))
#define PWR_CSR1        (*(volatile uint32_t *)(PWR_BASE + 0x04))

#define PWR_CR1_VOS      (3U << 14)
#define PWR_CR1_ODEN     (1U << 16)
#define PWR_CR1_ODSWEN   (1U << 17)
#define PWR_CSR1_ODRDY   (1U << 16)
#define PWR_CSR1_ODSWRDY (1U << 17)

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

/* GPIOK sits one port past J: 0x40020000 + 10 * 0x400 */
#define GPIOK_BASE      0x40022800UL
#define GPIOK_MODER     (*(volatile uint32_t *)(GPIOK_BASE + 0x00))
#define GPIOK_BSRR      (*(volatile uint32_t *)(GPIOK_BASE + 0x18))

#define LED_PIN         1     /* PI1,  LD1 green    */
#define DISP_PIN        12    /* PI12, LCD_DISP     */
#define BL_PIN          3     /* PK3,  LCD_BL_CTRL  */
#define TX_PIN          9     /* PA9,  VCP_TX       */

/* ------------------------------------------------------------------ */
/* USART1                                                              */
/* ------------------------------------------------------------------ */
#define USART1_BASE     0x40011000UL
#define USART1_CR1      (*(volatile uint32_t *)(USART1_BASE + 0x00))
#define USART1_BRR      (*(volatile uint32_t *)(USART1_BASE + 0x0C))
#define USART1_ISR      (*(volatile uint32_t *)(USART1_BASE + 0x1C))
#define USART1_TDR      (*(volatile uint32_t *)(USART1_BASE + 0x28))

#define USART_CR1_UE    (1U << 0)
#define USART_CR1_TE    (1U << 3)
#define USART_ISR_TXE   (1U << 7)

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

    RCC_PLLCFGR = (PLL_M << 0) | (PLL_N << 6) | (PLL_P << 16)
                | (1U << 22) | (PLL_Q << 24);

    RCC_CR |= RCC_CR_PLLON;

    PWR_CR1 |= PWR_CR1_ODEN;
    while (!(PWR_CSR1 & PWR_CSR1_ODRDY)) { }

    PWR_CR1 |= PWR_CR1_ODSWEN;
    while (!(PWR_CSR1 & PWR_CSR1_ODSWRDY)) { }

    FLASH_ACR = FLASH_ACR_LATENCY_7WS | FLASH_ACR_PRFTEN | FLASH_ACR_ARTEN;
    while ((FLASH_ACR & 0xFU) != FLASH_ACR_LATENCY_7WS) { }

    RCC_CFGR = (0U << 4) | (5U << 10) | (4U << 13);

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

    GPIOA_MODER &= ~(3U << (TX_PIN * 2));
    GPIOA_MODER |=  (2U << (TX_PIN * 2));
    GPIOA_OSPEEDR |= (3U << (TX_PIN * 2));

    GPIOA_AFRH &= ~(0xFU << ((TX_PIN - 8) * 4));
    GPIOA_AFRH |=  (7U   << ((TX_PIN - 8) * 4));

    /* Round to nearest: 108e6 / 115200 = 937.5 -> 938 */
    USART1_BRR = (APB2_HZ + BAUDRATE / 2U) / BAUDRATE;
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
            uart_putc('\r');
        }
        uart_putc(*s++);
    }
}

/* ------------------------------------------------------------------ */
/* The point of this project                                           */
/* ------------------------------------------------------------------ */
static void lcd_power_init(void)
{
    /* PI12 (LCD_DISP) and PK3 (LCD_BL_CTRL) live on two different ports,
     * so two clock enables. Forgetting GPIOKEN leaves the backlight
     * silently dead — the writes go nowhere, as ever. */
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOIEN | RCC_AHB1ENR_GPIOKEN;
    (void)RCC_AHB1ENR;

    /* Both as plain push-pull outputs: MODER = 01 */
    GPIOI_MODER &= ~(3U << (DISP_PIN * 2));
    GPIOI_MODER |=  (1U << (DISP_PIN * 2));

    GPIOK_MODER &= ~(3U << (BL_PIN * 2));
    GPIOK_MODER |=  (1U << (BL_PIN * 2));

    /* Panel first, backlight second. Lighting an unpowered panel shows
     * an ugly flash of noise before it settles. */
    GPIOI_BSRR = (1U << DISP_PIN);
    delay_ms(20);
    GPIOK_BSRR = (1U << BL_PIN);
}

static void led_init(void)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOIEN;
    (void)RCC_AHB1ENR;

    GPIOI_MODER &= ~(3U << (LED_PIN * 2));
    GPIOI_MODER |=  (1U << (LED_PIN * 2));
}

int main(void)
{
    clock_init();
    systick_init();
    uart_init();
    led_init();

    uart_puts("\nLCD power-up test\n");
    uart_puts("-----------------\n");

    uart_puts("PI12 LCD_DISP    -> high\n");
    uart_puts("PK3  LCD_BL_CTRL -> high\n");

    lcd_power_init();

    uart_puts("\nExpect an even pale grey screen.\n");
    uart_puts("Black means the panel or backlight is not coming up.\n");
    uart_puts("No LTDC yet, so no image — grey is the correct result.\n\n");

    /* Blink the backlight slowly, so it is unmistakable that the pin is
     * under software control and not just floating high. */
    while (1) {
        GPIOI_BSRR = (1U << LED_PIN);
        GPIOK_BSRR = (1U << BL_PIN);          /* backlight on  */
        delay_ms(2000);

        GPIOI_BSRR = (1U << (LED_PIN + 16));
        GPIOK_BSRR = (1U << (BL_PIN + 16));   /* backlight off */
        delay_ms(1000);

        uart_puts("backlight cycle\n");
    }
}
