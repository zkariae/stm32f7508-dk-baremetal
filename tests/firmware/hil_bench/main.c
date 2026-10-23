// SPDX-License-Identifier: MIT
/*!
****************************
\file       hil_bench/main.c
\brief      Entry point of the HIL protocol firmware.

\author     Z. BEN-AKKA
\version    1.1
\date       23/10/2026

\details
  Firmware of the hil-bench image, which implements tests/protocol.md.
  At boot it saves the reset cause first (section 4.2), starts USART1 at
  115200 baud and sends one READY banner (section 4.1). Bytes received
  before the end of the banner are discarded. The main loop then reads the
  UART receive events, assembles lines (line.c) and answers each request
  (dispatch.c). Only protocol records are sent on the link (section 2.3).
  UART driver diagnostics live in the separate uart-diag image
  (tests/firmware/uart_diag/).

\section hil_bench_main_c_version_history Version history
| Version | Date       | Author      | Description                                  |
|:-------:|:----------:|:------------|:---------------------------------------------|
| 1.0     | 22/10/2026 | Z. BEN-AKKA | Initial version: silent protocol entry point. |
| 1.1     | 23/10/2026 | Z. BEN-AKKA | Send the READY banner and serve protocol requests. |
****************************
*/

#include "board.h"
#include "dispatch.h"
#include "hil_protocol.h"
#include "line.h"
#include "protocol.h"
#include "reset_cause.h"

static LineAssembler line; ///< Zero-initialized: no line in progress.

/*!
\brief  Send the readiness banner (protocol.md section 4.1).
*/
static void SendBanner(void)
{
  Record banner;

  RecordBegin(&banner, HIL_REC_READY);
  RecordAdd(&banner, HIL_KEY_NAME, HIL_FW_NAME);
  RecordAdd(&banner, HIL_KEY_FW, HIL_FW_VERSION);
  RecordAdd(&banner, HIL_KEY_PROTO, HIL_PROTO_VERSION_STR);
  RecordAdd(&banner, HIL_KEY_BUILD, HIL_BUILD_ID);
  RecordAdd(&banner, HIL_KEY_RESET, ResetCauseToken());
  RecordAddHex32(&banner, HIL_KEY_RESET_FLAGS, ResetCauseFlags());
  RecordSend(&banner);
}

int main(void)
{
  ResetCauseCapture(); // Before anything else (section 4.2)

  UartInit(&BOARD_UART_VCP, HSI_HZ, HIL_UART_BAUDRATE); // No clock setup: the core runs from HSI at reset.
  UartRxStart(&BOARD_UART_VCP);

  SendBanner();
  UartFlush(&BOARD_UART_VCP);
  UartRxFlush(&BOARD_UART_VCP); // Drop the bytes received before the end of the banner

  for (;;) {
    UartRxEvent event;

    if (!UartRxGet(&BOARD_UART_VCP, &event)) {
      continue;
    }
    switch (LinePush(&line, event)) {
    case LINE_READY:
      DispatchLine(line.text);
      break;
    case LINE_TOO_LONG:
      DispatchFrameError(HIL_FRAME_LINE_TOO_LONG);
      break;
    case LINE_BAD_FRAME:
      DispatchFrameError(HIL_FRAME_BAD_FRAME);
      break;
    case LINE_NONE:
      break;
    }
  }
}
