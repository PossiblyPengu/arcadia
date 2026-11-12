#  SPDX-License-Identifier: MIT
#
#  ES-DE Frontend
#  CMakeLists.txt (es-pdf-converter)
#
#  CMake configuration for es-pdf-convert
#

project(es-pdf-convert)

    find_package(Poppler REQUIRED COMPONENTS cpp)

include_directories(${POPPLER_CPP_INCLUDE_DIR})
    set(CONVERTER_SOURCE_FILES ${CMAKE_CURRENT_SOURCE_DIR}/src/main.cpp
                               ${CMAKE_CURRENT_SOURCE_DIR}/src/ConvertPDF.cpp
                               ${CMAKE_CURRENT_SOURCE_DIR}/src/ConvertPDF.h)
    add_executable(es-pdf-convert WIN32 ${CONVERTER_SOURCE_FILES})
target_link_libraries(es-pdf-convert PRIVATE ${POPPLER_CPP_LIBRARY})

    set_target_properties(es-pdf-convert PROPERTIES INSTALL_RPATH_USE_LINK_PATH TRUE)
