#include <stdint.h>

/* --- RCC ------------------------------------------------------------- */
#define RCC_BASE        0x40023800UL
#define RCC_AHB1ENR     (*(volatile uint32_t *)(RCC_BASE + 0x30))
#define GPIOIEN         (1U << 8)        /* GPIOI is the 9th port: A=0 ... I=8 */

/* --- GPIOI ----------------------------------------------------------- */
/* GPIO ports are 0x400 apart from 0x40020000: I = 0x40020000 + 8*0x400 */
#define GPIOI_BASE      0x40022000UL
#define GPIOI_MODER     (*(volatile uint32_t *)(GPIOI_BASE + 0x00))
#define GPIOI_ODR       (*(volatile uint32_t *)(GPIOI_BASE + 0x14))

/* LD1, green, on PI1. Active high: writing 1 lights it.
 * Schematic MB1191 sheet 8: PI1 -> SB8 -> R59 (510R) -> LD1 -> GND
 */
#define LED             1

static void delay(volatile uint32_t n)
{
    while (n--) {
        __asm__("nop");
    }
}

int main(void)
{
    /* 1. Clock GPIOI. Without this, every write below is discarded. */
    RCC_AHB1ENR |= GPIOIEN;

    /* 2. PI1 as general-purpose output: MODER bits [3:2] = 01 */
    GPIOI_MODER &= ~(3U << (LED * 2));
    GPIOI_MODER |=  (1U << (LED * 2));

    /* 3. Toggle forever */
    while (1) {
        GPIOI_ODR ^= (1U << LED);
        delay(1000000);
    }
}