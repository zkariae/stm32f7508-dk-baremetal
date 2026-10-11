# SPDX-License-Identifier: MIT
# /*!
# ****************************
# \file       Makefile
# \brief      Repository-level targets; everything else goes to the board's Makefile.
#
# \author     Z. BEN-AKKA
# \version    1.1
# \date       11/10/2026
#
# \details
#   documentation  HTML documentation in work/doc/html (doxygen)
#   format         format the C sources (dev/scripts/format_cxx.sh)
#   Any other target goes to boards/$(BOARD)/Makefile, so
#   make 01-blink-flash works from here; pick a board with BOARD=<name>.
#
# \section root_makefile_version_history Version history
# | Version | Date       | Author      | Description                                       |
# |:-------:|:----------:|:------------|:--------------------------------------------------|
# | 1.0     | 10/10/2026 | Z. BEN-AKKA | Initial version.                                  |
# | 1.1     | 11/10/2026 | Z. BEN-AKKA | boards/ and dev/ layout; BOARD selects the board. |
# ****************************
# */

# Board to build for: a folder of boards/
BOARD ?= stm32f7508-dk

.DEFAULT_GOAL := help

# Make the documentation from board perspective
.PHONY: documentation
documentation:
	@rm -rf work/doc
	@mkdir -p work/doc
	@doxygen ./dev/scripts/Doxyfile
	@echo "work/doc/html/index.html ($$(wc -l < work/doc/doxygen.warnings) warning lines in work/doc/doxygen.warnings)"

# Format source files
.PHONY: format
format:
	@bash -c "dev/scripts/format_cxx.sh"

# The board's help, plus the targets above
.PHONY: help
help:
	@$(MAKE) --no-print-directory -C boards/$(BOARD) help
	@echo ""
	@echo "Repository:"
	@echo "  documentation        HTML documentation in work/doc/html (doxygen)"
	@echo "  format               format the sources (dev/scripts/format_cxx.sh)"
	@echo ""
	@echo "Board: $(BOARD) (boards/$(BOARD)); another one with BOARD=<name>"

# Any other target: hand it to the board's Makefile
%: FORCE
	@$(MAKE) --no-print-directory -C boards/$(BOARD) $@

.PHONY: FORCE
FORCE:

# Without this, make would try to rebuild this Makefile through the rule above
Makefile: ;
