#  SPDX-License-Identifier: MIT
#
#  Arcadia
#  CMakeLists.txt (es-app)
#
#  CMake configuration for es-app
#  Also contains the application packaging configuration.
#

project(arcadia)

set(ES_HEADERS
    ${CMAKE_CURRENT_SOURCE_DIR}/src/ApplicationUpdater.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/CollectionSystemsManager.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FileData.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FileFilterIndex.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FileSorts.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/GamelistFileParser.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MediaViewer.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MetaData.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MiximageGenerator.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/PlatformId.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/PDFViewer.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/Screensaver.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/SystemData.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/UIModeController.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/VolumeControl.h

    # GUIs
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiAlternativeEmulators.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiApplicationUpdater.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiCollectionSystemsOptions.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiGameImporter.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiGamelistFilter.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiGamelistOptions.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiLaunchScreen.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiMediaViewerOptions.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiMenu.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiMetaDataEd.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiOfflineGenerator.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiOrphanedDataCleanup.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScraperMenu.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScraperMulti.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScraperSearch.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScraperSingle.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScreensaverOptions.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiSettings.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiEmulators.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiSetup.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiToolRunner.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiSystemStatusOptions.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiThemeDownloader.h

    # Scrapers
    ${CMAKE_CURRENT_SOURCE_DIR}/src/scrapers/GamesDBJSONScraper.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/scrapers/GamesDBJSONScraperResources.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/scrapers/Scraper.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/scrapers/ScreenScraper.h

    # Views
    ${CMAKE_CURRENT_SOURCE_DIR}/src/views/GamelistBase.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/views/GamelistView.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/views/SystemView.h
    ${CMAKE_CURRENT_SOURCE_DIR}/src/views/ViewController.h
)

set(ES_SOURCES
    ${CMAKE_CURRENT_SOURCE_DIR}/src/ApplicationUpdater.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/CollectionSystemsManager.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FileData.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FileFilterIndex.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/FileSorts.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/GamelistFileParser.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/main.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MediaViewer.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MetaData.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/MiximageGenerator.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/PlatformId.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/PDFViewer.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/Screensaver.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/SystemData.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/UIModeController.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/VolumeControl.cpp

    # GUIs
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiAlternativeEmulators.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiApplicationUpdater.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiCollectionSystemsOptions.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiGameImporter.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiGamelistFilter.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiGamelistOptions.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiLaunchScreen.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiMenu.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiMediaViewerOptions.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiMetaDataEd.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiOfflineGenerator.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiOrphanedDataCleanup.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScraperMenu.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScraperMulti.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScraperSearch.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScraperSingle.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiScreensaverOptions.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiSettings.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiEmulators.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiSetup.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiToolRunner.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiSystemStatusOptions.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/guis/GuiThemeDownloader.cpp

    # Scrapers
    ${CMAKE_CURRENT_SOURCE_DIR}/src/scrapers/GamesDBJSONScraper.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/scrapers/GamesDBJSONScraperResources.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/scrapers/Scraper.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/scrapers/ScreenScraper.cpp

    # Views
    ${CMAKE_CURRENT_SOURCE_DIR}/src/views/GamelistBase.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/views/GamelistView.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/views/SystemView.cpp
    ${CMAKE_CURRENT_SOURCE_DIR}/src/views/ViewController.cpp
)

#---------------------------------------------------------------------------------------------------
# Target and installation (Linux only).

include_directories(${COMMON_INCLUDE_DIRS} ${CMAKE_CURRENT_SOURCE_DIR}/src)
add_executable(arcadia ${ES_SOURCES} ${ES_HEADERS})
target_link_libraries(arcadia ${COMMON_LIBRARIES} ${CMAKE_DL_LIBS} es-core lunasvg::lunasvg)
set_target_properties(arcadia PROPERTIES INSTALL_RPATH_USE_LINK_PATH TRUE)

install(TARGETS arcadia RUNTIME DESTINATION ${CMAKE_INSTALL_PREFIX}/bin)
install(FILES ${CMAKE_SOURCE_DIR}/LICENSE DESTINATION ${CMAKE_INSTALL_PREFIX}/share/arcadia)
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/assets/io.github.PossiblyPengu.Arcadia.desktop
    DESTINATION ${CMAKE_INSTALL_PREFIX}/share/applications)
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/assets/arcadia.svg
    DESTINATION ${CMAKE_INSTALL_PREFIX}/share/pixmaps)
install(FILES ${CMAKE_CURRENT_SOURCE_DIR}/assets/arcadia.svg
    DESTINATION ${CMAKE_INSTALL_PREFIX}/share/icons/hicolor/scalable/apps)
install(DIRECTORY ${CMAKE_SOURCE_DIR}/licenses DESTINATION ${CMAKE_INSTALL_PREFIX}/share/arcadia)
install(DIRECTORY ${CMAKE_SOURCE_DIR}/themes/arcadia
    ${CMAKE_SOURCE_DIR}/themes/linear-es-de
    ${CMAKE_SOURCE_DIR}/themes/modern-es-de
    DESTINATION ${CMAKE_INSTALL_PREFIX}/share/arcadia/themes)
install(DIRECTORY ${CMAKE_SOURCE_DIR}/resources DESTINATION ${CMAKE_INSTALL_PREFIX}/share/arcadia)
install(DIRECTORY ${CMAKE_SOURCE_DIR}/deck DESTINATION ${CMAKE_INSTALL_PREFIX}/share/arcadia USE_SOURCE_PERMISSIONS PATTERN "tests" EXCLUDE)
