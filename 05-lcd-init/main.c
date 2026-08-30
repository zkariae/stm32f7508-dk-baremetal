/*
 * 05-lcd-init
 *
 * Bring up the LTDC far enough to drive the panel with a solid colour.
 *
 * No framebuffer here, on purpose. LTDC_BCCR sets a background colour that
 * is emitted with no layer enabled and no memory involved, which separates
 * two hard problems: getting the timings and the twenty-eight pins right,
 * and finding somewhere to put 255 KB of pixels. The second one has a trap
 * waiting — the LTDC is an AHB master and cannot reach the DTCM at
 * 0x20000000, so the framebuffer has to live in SRAM1. That is the next
 * project.
 *
 * If the screen turns red, then green, then blue, the pixel clock, the
 * sync timings and every data line are correct.
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
#define RCC_PLLSAICFGR  (*(volatile uint32_t *)(RCC_BASE + 0x88))
#define RCC_DCKCFGR1    (*(volatile uint32_t *)(RCC_BASE + 0x8C))

#define RCC_CR_HSEON      (1U << 16)
#define RCC_CR_HSERDY     (1U << 17)
#define RCC_CR_PLLON      (1U << 24)
#define RCC_CR_PLLRDY     (1U << 25)
#define RCC_CR_PLLSAION   (1U << 28)
#define RCC_CR_PLLSAIRDY  (1U << 29)

#define RCC_APB1ENR_PWREN    (1U << 28)
#define RCC_APB2ENR_USART1EN (1U << 4)
#define RCC_APB2ENR_LTDCEN   (1U << 26)

#define GPIOA_EN  (1U << 0)
#define GPIOE_EN  (1U << 4)
#define GPIOG_EN  (1U << 6)
#define GPIOI_EN  (1U << 8)
#define GPIOJ_EN  (1U << 9)
#define GPIOK_EN  (1U << 10)

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
/* GPIO — ports are 0x400 apart from 0x40020000                        */
/* ------------------------------------------------------------------ */
#define GPIO_PORT(n)    (0x40020000UL + (n) * 0x400UL)
#define PORT_A  0
#define PORT_E  4
#define PORT_G  6
#define PORT_I  8
#define PORT_J  9
#define PORT_K  10

#define GPIO_MODER(p)   (*(volatile uint32_t *)(GPIO_PORT(p) + 0x00))
#define GPIO_OSPEEDR(p) (*(volatile uint32_t *)(GPIO_PORT(p) + 0x08))
#define GPIO_BSRR(p)    (*(volatile uint32_t *)(GPIO_PORT(p) + 0x18))
#define GPIO_AFRL(p)    (*(volatile uint32_t *)(GPIO_PORT(p) + 0x20))
#define GPIO_AFRH(p)    (*(volatile uint32_t *)(GPIO_PORT(p) + 0x24))

/* ------------------------------------------------------------------ */
/* USART1 on PA9                                                       */
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
/* LTDC — RM0385 section 18                                            */
/* ------------------------------------------------------------------ */
#define LTDC_BASE       0x40016800UL
#define LTDC_SSCR       (*(volatile uint32_t *)(LTDC_BASE + 0x08))
#define LTDC_BPCR       (*(volatile uint32_t *)(LTDC_BASE + 0x0C))
#define LTDC_AWCR       (*(volatile uint32_t *)(LTDC_BASE + 0x10))
#define LTDC_TWCR       (*(volatile uint32_t *)(LTDC_BASE + 0x14))
#define LTDC_GCR        (*(volatile uint32_t *)(LTDC_BASE + 0x18))
#define LTDC_SRCR       (*(volatile uint32_t *)(LTDC_BASE + 0x24))
#define LTDC_BCCR       (*(volatile uint32_t *)(LTDC_BASE + 0x2C))
#define LTDC_CDSR       (*(volatile uint32_t *)(LTDC_BASE + 0x48))

#define LTDC_GCR_LTDCEN (1U << 0)
#define LTDC_SRCR_IMR   (1U << 0)

/* ------------------------------------------------------------------ */
/* Panel: RK043FN48H, 480x272                                          */
/*                                                                     */
/* The datasheet gives Thbp = 43 and Tvbp = 12 typical, with periods of */
/* 531 and 288. Those only add up if the back porch figures already     */
/* include the sync pulse:                                             */
/*                                                                     */
/*    1 + 42 + 480 +  8 = 531   horizontal                             */
/*   10 +  2 + 272 +  4 = 288   vertical                               */
/*                                                                     */
/* which is the reading used here.                                     */
/* ------------------------------------------------------------------ */
#define LCD_WIDTH   480U
#define LCD_HEIGHT  272U

#define HSW   1U        /* horizontal sync width, in pixel clocks */
#define HBP   42U       /* horizontal back porch                  */
#define HFP   8U        /* horizontal front porch                 */

#define VSW   10U       /* vertical sync width, in lines          */
#define VBP   2U        /* vertical back porch                    */
#define VFP   4U        /* vertical front porch                   */

/* ------------------------------------------------------------------ */
/* Clocks                                                              */
/*                                                                     */
/* System: HSE 25 / 25 * 432 / 2 = 216 MHz                             */
/* Pixel : HSE 25 / 25 * 288 / 4 / 8 = 9 MHz                           */
/*                                                                     */
/* PLLM is shared, so the PLLSAI VCO input is 1 MHz and PLLSAIN must be */
/* at least 192 to keep the VCO inside its 192..432 MHz window.        */
/* ------------------------------------------------------------------ */
#define PLL_M   25U
#define PLL_N   432U
#define PLL_P   0U
#define PLL_Q   9U

#define PLLSAI_N     288U   /* VCO = 288 MHz  */
#define PLLSAI_R     4U     /* PLLSAI_R = 72 MHz */
#define PLLSAI_DIVR  2U     /* code 10 = /8 -> 9 MHz */

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

/* ------------------------------------------------------------------ */
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

/* The LTDC does not run off SYSCLK. It needs its own pixel clock,
 * produced by a second PLL and divided once more on the way out. */
static void pllsai_init(void)
{
    /* PLLSAICFGR may only be written while the PLLSAI is stopped */
    RCC_CR &= ~RCC_CR_PLLSAION;
    while (RCC_CR & RCC_CR_PLLSAIRDY) { }

    RCC_PLLSAICFGR = (PLLSAI_N << 6) | (PLLSAI_R << 28);

    /* PLLSAIDIVR sits in bits [17:16]: 00=/2, 01=/4, 10=/8, 11=/16 */
    RCC_DCKCFGR1 = (RCC_DCKCFGR1 & ~(3U << 16)) | (PLLSAI_DIVR << 16);

    RCC_CR |= RCC_CR_PLLSAION;
    while (!(RCC_CR & RCC_CR_PLLSAIRDY)) { }
}

static void systick_init(void)
{
    SYST_RVR = (SYSCLK_HZ / 1000U) - 1U;
    SYST_CVR = 0;
    SYST_CSR = SYST_CSR_CLKSOURCE | SYST_CSR_TICKINT | SYST_CSR_ENABLE;
}

/* ------------------------------------------------------------------ */
/* One helper instead of twenty-eight copies of the same four lines.   */
/* ------------------------------------------------------------------ */
static void pin_af(uint32_t port, uint32_t pin, uint32_t af)
{
    /* Alternate function mode: MODER = 10 */
    GPIO_MODER(port) &= ~(3U << (pin * 2));
    GPIO_MODER(port) |=  (2U << (pin * 2));

    /* Very high speed — a 9 MHz clock with slow edges smears the data */
    GPIO_OSPEEDR(port) |= (3U << (pin * 2));

    /* Pins 0..7 live in AFRL, 8..15 in AFRH, four bits each */
    if (pin < 8U) {
        GPIO_AFRL(port) &= ~(0xFU << (pin * 4));
        GPIO_AFRL(port) |=  (af   << (pin * 4));
    } else {
        GPIO_AFRH(port) &= ~(0xFU << ((pin - 8U) * 4));
        GPIO_AFRH(port) |=  (af   << ((pin - 8U) * 4));
    }
}

static void pin_output(uint32_t port, uint32_t pin)
{
    GPIO_MODER(port) &= ~(3U << (pin * 2));
    GPIO_MODER(port) |=  (1U << (pin * 2));
}

/* Every LTDC signal on this board, straight from the MB1191 schematic.
 * All of them are AF14. */
static const struct { uint8_t port, pin; } ltdc_pins[] = {
    /* Red */
    { PORT_I, 15 }, { PORT_J, 0 }, { PORT_J, 1 }, { PORT_J, 2 },
    { PORT_J, 3 },  { PORT_J, 4 }, { PORT_J, 5 }, { PORT_J, 6 },
    /* Green */
    { PORT_J, 7 },  { PORT_J, 8 }, { PORT_J, 9 }, { PORT_J, 10 },
    { PORT_J, 11 }, { PORT_K, 0 }, { PORT_K, 1 }, { PORT_K, 2 },
    /* Blue */
    { PORT_E, 4 },  { PORT_J, 13 }, { PORT_J, 14 }, { PORT_J, 15 },
    { PORT_G, 12 }, { PORT_K, 4 },  { PORT_K, 5 },  { PORT_K, 6 },
    /* Control */
    { PORT_I, 10 },  /* HSYNC */
    { PORT_I, 9 },   /* VSYNC */
    { PORT_I, 14 },  /* CLK   */
    { PORT_K, 7 },   /* DE    */
};

#define LTDC_PIN_COUNT (sizeof(ltdc_pins) / sizeof(ltdc_pins[0]))

static void ltdc_pins_init(void)
{
    RCC_AHB1ENR |= GPIOE_EN | GPIOG_EN | GPIOI_EN | GPIOJ_EN | GPIOK_EN;
    (void)RCC_AHB1ENR;

    for (uint32_t i = 0; i < LTDC_PIN_COUNT; i++) {
        pin_af(ltdc_pins[i].port, ltdc_pins[i].pin, 14U);
    }
}

static void lcd_power_on(void)
{
    pin_output(PORT_I, 12);          /* LCD_DISP    */
    pin_output(PORT_K, 3);           /* LCD_BL_CTRL */

    GPIO_BSRR(PORT_I) = (1U << 12);
    delay_ms(20);
    GPIO_BSRR(PORT_K) = (1U << 3);
}

static void ltdc_init(void)
{
    RCC_APB2ENR |= RCC_APB2ENR_LTDCEN;
    (void)RCC_APB2ENR;

    /* Every timing register holds an accumulated total, minus one.
     * Getting this wrong gives a rolling or torn image rather than
     * nothing at all, which is a useful thing to recognise. */
    LTDC_SSCR = ((HSW - 1U) << 16) | (VSW - 1U);
    LTDC_BPCR = ((HSW + HBP - 1U) << 16) | (VSW + VBP - 1U);
    LTDC_AWCR = ((HSW + HBP + LCD_WIDTH - 1U) << 16)
              | (VSW + VBP + LCD_HEIGHT - 1U);
    LTDC_TWCR = ((HSW + HBP + LCD_WIDTH + HFP - 1U) << 16)
              | (VSW + VBP + LCD_HEIGHT + VFP - 1U);

    /* Polarities: this panel wants HSYNC and VSYNC active low, DE active
     * low and a non-inverted pixel clock — which is the reset state of
     * all four bits, so nothing to set. */

    LTDC_BCCR = 0x000000FFU;         /* start on blue */

    LTDC_SRCR = LTDC_SRCR_IMR;       /* commit the shadow registers */
    LTDC_GCR |= LTDC_GCR_LTDCEN;
}

/* ------------------------------------------------------------------ */
/* UART, so the board can report what it found                         */
/* ------------------------------------------------------------------ */
static void uart_init(void)
{
    RCC_AHB1ENR |= GPIOA_EN;
    RCC_APB2ENR |= RCC_APB2ENR_USART1EN;
    (void)RCC_APB2ENR;

    pin_af(PORT_A, 9, 7U);

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

static void uart_hex32(uint32_t v)
{
    static const char digits[] = "0123456789ABCDEF";
    uart_puts("0x");
    for (int shift = 28; shift >= 0; shift -= 4) {
        uart_putc(digits[(v >> shift) & 0xFU]);
    }
}

static void uart_dec(uint32_t v)
{
    char buf[11];
    int i = 0;

    if (v == 0) { uart_putc('0'); return; }
    while (v > 0) { buf[i++] = (char)('0' + (v % 10U)); v /= 10U; }
    while (i > 0) { uart_putc(buf[--i]); }
}

/* ------------------------------------------------------------------ */
int main(void)
{
    clock_init();
    systick_init();
    uart_init();

    uart_puts("\nLTDC bring-up\n");
    uart_puts("-------------\n");

    pllsai_init();
    uart_puts("PLLSAI locked, pixel clock 9 MHz\n");

    ltdc_pins_init();
    uart_puts("28 pins set to AF14\n");

    lcd_power_on();
    uart_puts("panel and backlight on\n");

    ltdc_init();
    uart_puts("LTDC enabled\n\n");

    uart_puts("LTDC_SSCR = "); uart_hex32(LTDC_SSCR); uart_puts("\n");
    uart_puts("LTDC_BPCR = "); uart_hex32(LTDC_BPCR); uart_puts("\n");
    uart_puts("LTDC_AWCR = "); uart_hex32(LTDC_AWCR); uart_puts("\n");
    uart_puts("LTDC_TWCR = "); uart_hex32(LTDC_TWCR); uart_puts("\n");
    uart_puts("LTDC_GCR  = "); uart_hex32(LTDC_GCR);  uart_puts("\n");

    /* Refresh rate, worked out from the numbers actually programmed */
    uint32_t total_w = HSW + HBP + LCD_WIDTH + HFP;
    uint32_t total_h = VSW + VBP + LCD_HEIGHT + VFP;
    uart_puts("\nframe = ");
    uart_dec(total_w);
    uart_puts(" x ");
    uart_dec(total_h);
    uart_puts(" -> ");
    uart_dec(9000000U / (total_w * total_h));
    uart_puts(" Hz\n\n");

    /* Cycling the background proves the LTDC is generating a real frame:
     * a still colour could in principle be a stuck data line. */
    static const uint32_t colours[] = {
        0x00FF0000U,   /* red   */
        0x0000FF00U,   /* green */
        0x000000FFU,   /* blue  */
        0x00FFFFFFU,   /* white */
    };
    static const char *names[] = { "red", "green", "blue", "white" };

    uint32_t i = 0;
    while (1) {
        LTDC_BCCR = colours[i];
        LTDC_SRCR = LTDC_SRCR_IMR;

        uart_puts(names[i]);
        uart_puts("  CDSR = ");
        uart_hex32(LTDC_CDSR);
        uart_puts("\n");

        i = (i + 1U) % 4U;
        delay_ms(1500);
    }
}
