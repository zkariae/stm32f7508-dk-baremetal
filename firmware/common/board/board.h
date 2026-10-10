// SPDX-License-Identifier: MIT
/*!
****************************
\file       common/board/board.h
\brief      STM32F7508-DK: on-board LED, console, LCD panel and QSPI flash.

\author     Z. BEN-AKKA
\version    1.0
\date       10/10/2026

\details
  Everything specific to this board, built on the generic drivers: the
  BOARD_xxx descriptors are passed to them, the Boardxxx() functions do the
  wiring-dependent setup. Pin numbers come from defines.h (UM2470, MB1191).

\section board_h_version_history Version history
| Version | Date       | Author      | Description      |
|:-------:|:----------:|:------------|:-----------------|
| 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version. |
****************************
*/

#ifndef BOARD_H
#define BOARD_H

#include "led/led.h"
#include "ltdc/ltdc.h"
#include "uart/uart.h"

extern const Led BOARD_LED_LD1;           ///< LD1 green, PI1, active high.
extern const Uart BOARD_UART_VCP;         ///< USART1 TX on PA9, to the ST-LINK virtual COM port.
extern const LtdcTiming BOARD_LCD_TIMING; ///< RK043FN48H panel, 480x272.

/*!
\brief  Clock the ports and set the 28 LTDC signals of the panel to AF14.
*/
void BoardLcdPinsInit(void);

/*!
\brief  Enable the panel (PI12), then its backlight (PK3) 20 ms later.
\details Uses DelayMs(): SysTick must be running.
*/
void BoardLcdPowerOn(void);

/*!
\brief  Switch the panel backlight on.
*/
void BoardLcdBacklightOn(void);

/*!
\brief  Switch the panel backlight off.
*/
void BoardLcdBacklightOff(void);

/*!
\brief  Clock the ports and set the six QSPI flash signals to their AF.
*/
void BoardQspiPinsInit(void);

#endif
