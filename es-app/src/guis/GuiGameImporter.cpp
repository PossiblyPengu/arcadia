//  SPDX-License-Identifier: MIT
//
//  ES-DE Frontend
//  GuiGameImporter.cpp
//
//  Game import utility.
//

#include "guis/GuiGameImporter.h"

#include "Log.h"
#include "resources/Font.h"

#include <SDL2/SDL_timer.h>


#define MAX_FILE_SIZE 1048576
#define CHECKED_PATH ":/graphics/checkbox_checked.svg"
#define UNCHECKED_PATH ":/graphics/checkbox_unchecked.svg"

GuiGameImporter::GuiGameImporter(std::string title, std::function<void()> updateCallback)
    : mRenderer {Renderer::getInstance()}
    , mUpdateCallback(updateCallback)
    , mMenu {title}
    , mNoConfig {false}
    , mSelectorWindow {false}
    , mHasUpdates {false}
    , mAndroidGetApps {false}
    , mIsInventorying {false}
    , mDoneInventorying {false}
    , mHasEntries {false}
{
    mTempDir = Utils::FileSystem::getAppDataDirectory() + "/importer_temp";
    Utils::FileSystem::removeDirectory(mTempDir, true);

    mTargetSystem =
        std::make_shared<OptionListComponent<std::string>>(_("IMPORT TO SYSTEM"), false);

    std::string selectedSystem {Settings::getInstance()->getString("ImporterTargetSystem")};

    for (auto& importRule : SystemData::sImportRules.get()->mSystems) {
        if (!importRule.second.validSystem) {
            LOG(LogWarning) << "GuiGameImporter: Skipping configuration entry for invalid system \""
                            << importRule.first << "\"";
            continue;
        }
        mTargetSystem->add(Utils::String::toUpper(importRule.second.fullName), importRule.first,
                           selectedSystem == importRule.first);
    }

    mMenu.addSaveFunc([this] {
        if (mTargetSystem->getSelected() !=
            Settings::getInstance()->getString("ImporterTargetSystem")) {
            Settings::getInstance()->setString("ImporterTargetSystem",
                                               mTargetSystem->getSelected());
            mMenu.setNeedsSaving();
        }
    });

    if (mTargetSystem->getNumEntries() == 0) {
        mTargetSystem->add(_("NO CONFIGURATION"), "noconfig", selectedSystem == "noconfig");
        mNoConfig = true;
    }
    else if (mTargetSystem->getSelectedObjects().size() == 0) {
        mTargetSystem->selectEntry(0);
    }

    mMenu.addWithLabel(_("IMPORT TO SYSTEM"), mTargetSystem);

    mRemoveEntries = std::make_shared<OptionListComponent<std::string>>(_("REMOVE ENTRIES"), false);
    std::string selectedRemoveEntries {Settings::getInstance()->getString("ImporterRemoveEntries")};
    mRemoveEntries->add(_("NEVER"), "never", selectedRemoveEntries == "never");
    mRemoveEntries->add(_("ALL UNSELECTED"), "unselected", selectedRemoveEntries == "unselected");
    mMenu.addSaveFunc([this] {
        if (mRemoveEntries->getSelected() !=
            Settings::getInstance()->getString("ImporterRemoveEntries")) {
            Settings::getInstance()->setString("ImporterRemoveEntries",
                                               mRemoveEntries->getSelected());
            mMenu.setNeedsSaving();
        }
    });

    if (mRemoveEntries->getSelectedObjects().size() == 0)
        mRemoveEntries->selectEntry(0);

    mMenu.addWithLabel(_("REMOVE ENTRIES"), mRemoveEntries);

    mStripSpecialChars = std::make_shared<SwitchComponent>();
    mStripSpecialChars->setState(Settings::getInstance()->getBool("ImporterStripSpecialChars"));
    mMenu.addWithLabel(_("STRIP SPECIAL CHARACTERS"), mStripSpecialChars);
    mMenu.addSaveFunc([this] {
        if (mStripSpecialChars->getState() !=
            Settings::getInstance()->getBool("ImporterStripSpecialChars")) {
            Settings::getInstance()->setBool("ImporterStripSpecialChars",
                                             mStripSpecialChars->getState());
            mMenu.setNeedsSaving();
        }
    });


    mMenu.addButton(_("START"), _("start importer"),
                    std::bind(&GuiGameImporter::pressedStart, this));
    mMenu.addButton(_("BACK"), _("back"), [&] { delete this; });

    if (mNoConfig) {
        mTargetSystem->selectEntry(0);
        mTargetSystem->setEnabled(false);
        mTargetSystem->setOpacity(DISABLED_OPACITY);
        mTargetSystem->getParent()
            ->getChild(mTargetSystem->getChildIndex() - 1)
            ->setOpacity(DISABLED_OPACITY);

        mRemoveEntries->setEnabled(false);
        mRemoveEntries->setOpacity(DISABLED_OPACITY);
        mRemoveEntries->getParent()
            ->getChild(mRemoveEntries->getChildIndex() - 1)
            ->setOpacity(DISABLED_OPACITY);
        mStripSpecialChars->setEnabled(false);
        mStripSpecialChars->setOpacity(DISABLED_OPACITY);
        mStripSpecialChars->getParent()
            ->getChild(mStripSpecialChars->getChildIndex() - 1)
            ->setOpacity(DISABLED_OPACITY);
        mMenu.setButtonOpacity(0, 0.5f);
    }

    setSize(mMenu.getSize());

    setPosition((mRenderer->getScreenWidth() - mSize.x) / 2.0f,
                mRenderer->getScreenHeight() * 0.13f);

    mBusyAnim.setSize(mSize);
    mBusyAnim.setText(_("WORKING..."));
    mBusyAnim.onSizeChanged();

    mainWindow();
}

GuiGameImporter::~GuiGameImporter()
{
    mIsInventorying = false;

    if (mImportThread) {
        mImportThread->join();
        mImportThread.reset();
    }

    Utils::FileSystem::removeDirectory(mTempDir, true);
    mWindow->stopInfoPopup();

    if (mHasUpdates && mUpdateCallback)
        mUpdateCallback();
}

void GuiGameImporter::update(int deltaTime)
{
    if (mIsInventorying)
        mBusyAnim.update(deltaTime);


    if (mDoneInventorying) {
        // We call this just to reset the busy indicator to the first animation frame, in case
        // multiple imports are done by the user.
        mBusyAnim.onSizeChanged();

        mIsInventorying = false;
        mDoneInventorying = false;
        if (mHasEntries) {
            mHasEntries = false;
            selectorWindow();
        }
        else {
            mWindow->pushGui(new GuiMsgBox(
                _("COULDN'T FIND ANYTHING TO IMPORT"), _("OK"), [] {}, "", nullptr, "", nullptr, "",
                nullptr, nullptr, true, true));
        }
    }

    GuiComponent::update(deltaTime);
}

void GuiGameImporter::render(const glm::mat4& parentTrans)
{
    glm::mat4 trans {parentTrans * getTransform()};
    renderChildren(trans);

    if (mIsInventorying)
        mBusyAnim.render(trans);
}

std::vector<HelpPrompt> GuiGameImporter::getHelpPrompts()
{
    if (mSelectorWindow) {
        std::vector<HelpPrompt> prompts {mSelectorMenu->getHelpPrompts()};
        prompts.push_back(HelpPrompt("b", _("cancel")));
        return prompts;
    }
    else {
        std::vector<HelpPrompt> prompts {mMenu.getHelpPrompts()};
        prompts.push_back(HelpPrompt("b", _("back")));
        prompts.push_back(HelpPrompt("y", _("start importer")));
        return prompts;
    }
}

void GuiGameImporter::pressedStart()
{
    if (mNoConfig)
        return;

    Utils::FileSystem::removeDirectory(mTempDir, true);

    mTargetSystemDir = mTargetSystem->getSelected();
    mFileExtension = "";

    for (auto& importRule : SystemData::sImportRules.get()->mSystems) {
        if (importRule.first == mTargetSystemDir) {
            mFileExtension = importRule.second.extension;
            break;
        }
    }

    auto importFunc = [this]() {
        if (mImportThread) {
            mImportThread->join();
            mImportThread.reset();
        }

        mMediaFileExtension = "";

        for (auto& importRule : SystemData::sImportRules.get()->mSystems) {
            if (importRule.first == mTargetSystemDir) {
                if (importRule.second.ruleType == "androidpackage") {
                    mMediaFileExtension = ".png";
                    std::vector<std::pair<std::string, std::string>> appList;
                    // Due to JNI weirdness on Android where there are issues with SDL if
                    // attempting to run the app retrieval in a separate thread we instead need
                    // to run this on the main thread. We set a flag to execute it from the
                    // update() function which is just a hack to make sure a static busy
                    // indicator is rendered before calling the retrieval function.
                    mAndroidGetApps = true;
                }
                else if (importRule.second.ruleType == "file") {
                    mImportThread =
                        std::make_unique<std::thread>(&GuiGameImporter::fileRule, this, importRule);
                }
                else if (importRule.second.ruleType == "desktopshortcut") {
                    mImportThread = std::make_unique<std::thread>(
                        &GuiGameImporter::desktopshortcutRule, this, importRule);
                }
                break;
            }
        }
    };

    if (mRemoveEntries->getSelected() == "unselected") {
        mWindow->pushGui(new GuiMsgBox(
            Utils::String::format(
                _("YOU HAVE CHOSEN TO REMOVE ALL UNSELECTED ENTRIES, THIS WILL DELETE "
                  "ALL GAME FILES WITH THE \"%s\" FILE EXTENSION FROM THE \"%s\" SYSTEM DIRECTORY "
                  "AND THEN IMPORT THE ENTRIES YOU SELECT ON THE NEXT SCREEN\nARE YOU SURE?"),
                mFileExtension.c_str(), mTargetSystem->getSelected().c_str()),
            _("YES"), [importFunc] { importFunc(); }, _("NO"), nullptr, "", nullptr, "", nullptr,
            nullptr, false, true,
            (mRenderer->getIsVerticalOrientation() ?
                 0.94f :
                 0.60f * (1.778f / mRenderer->getScreenAspectRatio()))));
    }
    else {
        importFunc();
    }
}

void GuiGameImporter::mainWindow()
{
    mSelectorMenu.reset();
    mSelectorWindow = false;
    addChild(&mMenu);
    mWindow->setHelpPrompts(getHelpPrompts());
}

void GuiGameImporter::selectorWindow()
{
    removeChild(&mMenu);

    mSelectorMenu = std::make_unique<MenuComponent>(_("MAKE YOUR SELECTION"));
    addChild(mSelectorMenu.get());

    mCheckboxes.clear();
    ComponentListRow row;

    auto spacer = std::make_shared<GuiComponent>();
    spacer->setSize(mRenderer->getScreenWidth() * 0.005f, 0.0f);

    std::string imagePath;
    std::list<std::string> inputFileList {Utils::FileSystem::getDirContent(mTempDir + "/files")};

    // Always use case-insensitive sorting of the actual filename exluding its path and extension.
    inputFileList.sort([](std::string a, std::string b) {
        std::string aFile {Utils::FileSystem::getStem(Utils::FileSystem::getFileName(a))};
        std::string bFile {Utils::FileSystem::getStem(Utils::FileSystem::getFileName(b))};
        return Utils::String::toUpper(aFile) < Utils::String::toUpper(bFile);
    });

    LOG(LogDebug) << "GuiGameImporter::selectorWindow(): Retrieved " << inputFileList.size()
                  << (inputFileList.size() == 1 ? " entry" : " entries") << " for system \""
                  << mTargetSystemDir << "\"";

    std::vector<std::pair<std::string, std::string>> fileList;


    for (std::string& file : inputFileList) {

        row.elements.clear();
        auto lbl = std::make_shared<TextComponent>(
            Utils::FileSystem::getStem(Utils::FileSystem::getFileName(file)),
            Font::get(FONT_SIZE_MEDIUM), mMenuColorPrimary);

        fileList.emplace_back(std::make_pair(file, ""));

        auto checkbox = std::make_shared<ImageComponent>();
        checkbox->setResize(0, Font::get(FONT_SIZE_MEDIUM)->getLetterHeight());
        checkbox->setImage(UNCHECKED_PATH);
        checkbox->setColorShift(mMenuColorPrimary);
        checkbox->setEnabled(false);
        mCheckboxes.emplace_back(checkbox);

        row.addElement(lbl, true);
        row.addElement(checkbox, false);
        row.makeAcceptInputHandler([checkbox] {
            if (checkbox->getEnabled()) {
                checkbox->setEnabled(false);
                checkbox->setImage(UNCHECKED_PATH);
            }
            else {
                checkbox->setEnabled(true);
                checkbox->setImage(CHECKED_PATH);
            }
        });
        mSelectorMenu->addRow(row);
    }

    mSelectorMenu->addButton(_("IMPORT"), _("import"), [this, fileList] {
        const std::string removeEntries {mRemoveEntries->getSelected()};
        int numEntriesImported {0};

        if (removeEntries == "unselected") {
            for (auto& file : Utils::FileSystem::getDirContent(
                     FileData::getROMDirectory() + mTargetSystemDir, false)) {
                if (Utils::FileSystem::getExtension(file) == mFileExtension) {
                    LOG(LogInfo) << "GuiGameImporter: Removed file \"" << file << "\"";
                    Utils::FileSystem::removeFile(file);
                }
            }
        }

        for (int i {0}; i < static_cast<int>(mCheckboxes.size()); ++i) {
            const std::string systemDir {FileData::getROMDirectory() + mTargetSystemDir};
            if (!Utils::FileSystem::exists(systemDir))
                Utils::FileSystem::createDirectory(systemDir);

            if (!Utils::FileSystem::exists(systemDir))
                return;


            if (mCheckboxes[i]->getEnabled()) {
                mHasUpdates = true;
                ++numEntriesImported;

                const std::string file {fileList[i].first};
                if (Utils::FileSystem::exists(file)) {
                    // We have to copy and not rename the files as they may need to move across
                    // different storage devices.
                    Utils::FileSystem::copyFile(
                        file, systemDir + "/" + Utils::FileSystem::getFileName(file), true);
                    Utils::FileSystem::removeFile(file);

                    LOG(LogInfo) << "GuiGameImporter: Importing \""
                                 << Utils::FileSystem::getStem(Utils::FileSystem::getFileName(file))
                                 << "\"";

                }
            }
        }

        if (mHasUpdates) {
            LOG(LogInfo) << "GuiGameImporter: Imported " << numEntriesImported
                         << (numEntriesImported == 1 ? " entry" : " entries") << " for system \""
                         << mTargetSystemDir << "\"";
            mWindow->queueInfoPopup(
                Utils::String::format(
                    _n("IMPORTED %i ENTRY", "IMPORTED %i ENTRIES", numEntriesImported),
                    numEntriesImported),
                4000);
            removeChild(mSelectorMenu.get());
            mainWindow();
        }
    });

    mSelectorMenu->addButton(_("CANCEL"), _("cancel"), [this] {
        removeChild(mSelectorMenu.get());
        mainWindow();
    });
    mSelectorMenu->addButton(_("SELECT ALL"), _("select all"), [this] {
        for (auto& checkbox : mCheckboxes) {
            checkbox->setEnabled(true);
            checkbox->setImage(CHECKED_PATH);
        }
    });

    mSelectorMenu->addButton(_("SELECT NONE"), _("select none"), [this] {
        for (auto& checkbox : mCheckboxes) {
            checkbox->setEnabled(false);
            checkbox->setImage(UNCHECKED_PATH);
        }
    });

    mSelectorWindow = true;
    mWindow->setHelpPrompts(getHelpPrompts());
}

void GuiGameImporter::androidpackageRule(std::vector<std::pair<std::string, std::string>> appList)
{
    mHasEntries = false;
    mIsInventorying = true;

    bool hasEntries {false};

    // This is just so that the busy component gets shown briefly regardless of processing time.
    SDL_Delay(400);


    mHasEntries = hasEntries;
    mIsInventorying = false;
    mDoneInventorying = true;
}

void GuiGameImporter::fileRule(std::pair<const std::string, ImportRules::ImportRule> importRule)
{
    mHasEntries = false;
    mIsInventorying = true;
    SDL_Delay(700);

    const std::string filesDir {mTempDir + "/files"};
    if (!Utils::FileSystem::exists(filesDir))
        Utils::FileSystem::createDirectory(filesDir);
    if (!Utils::FileSystem::exists(filesDir)) {
        mIsInventorying = false;
        mDoneInventorying = true;
        LOG(LogError) << "GuiGameImporter: Couldn't create temporary files directory";
        return;
    }

    bool hasEntries {false};

    for (auto& directory : importRule.second.directories) {
        // Expand ~ to the user home directory.
        std::string expandedDir {Utils::FileSystem::expandHomePath(directory.path, true)};
        // Expand %ESPATH% to the ES-DE binary directory.
        expandedDir =
            Utils::String::replace(expandedDir, "%ESPATH%", Utils::FileSystem::getExePath());

        std::list<std::string> fileList {
            Utils::FileSystem::getDirContent(expandedDir, directory.recursive)};
        for (auto& file : fileList) {
            if (Utils::FileSystem::getExtension(file) == mFileExtension) {
                if (Utils::FileSystem::isDirectory(file)) {
                    LOG(LogWarning) << "GuiGameImporter: Skipping \"" << file
                                    << "\" as it's a directory and not a file";
                    continue;
                }

                const long fileSize {Utils::FileSystem::getFileSize(file)};
                if (fileSize > MAX_FILE_SIZE) {
                    LOG(LogWarning) << "GuiGameImporter: File \"" << file << "\" is too big at "
                                    << fileSize << " bytes, skipping it";
                    continue;
                }

                if (Utils::FileSystem::getFileName(file) == "org.es_de.frontend.desktop")
                    continue;
                std::string targetFile {file};
                hasEntries = true;
                int index {1};

                // Add an index number to the filename in case there are multiple files with the
                // same name.
                while (Utils::FileSystem::exists(filesDir + "/" +
                                                 Utils::FileSystem::getFileName(targetFile))) {
                    targetFile = {Utils::FileSystem::getParent(file)};
                    targetFile.append("/")
                        .append(Utils::FileSystem::getStem(Utils::FileSystem::getFileName(file)))
                        .append(" (")
                        .append(std::to_string(index))
                        .append(")")
                        .append(Utils::FileSystem::getExtension(file));
                    ++index;
                }

                Utils::FileSystem::copyFile(
                    file, filesDir + "/" + Utils::FileSystem::getFileName(targetFile), false);
            }
        }
    }

    mHasEntries = hasEntries;
    mIsInventorying = false;
    mDoneInventorying = true;
}

void GuiGameImporter::desktopshortcutRule(
    std::pair<const std::string, ImportRules::ImportRule> importRule)
{
    mHasEntries = false;
    mIsInventorying = true;
    SDL_Delay(700);

    const std::string filesDir {mTempDir + "/files"};
    if (!Utils::FileSystem::exists(filesDir))
        Utils::FileSystem::createDirectory(filesDir);
    if (!Utils::FileSystem::exists(filesDir)) {
        mIsInventorying = false;
        mDoneInventorying = true;
        LOG(LogError) << "GuiGameImporter: Couldn't create temporary files directory";
        return;
    }

    bool hasEntries {false};

    for (auto& directory : importRule.second.directories) {
        // Expand ~ to the user home directory.
        std::string expandedDir {Utils::FileSystem::expandHomePath(directory.path, true)};

        std::list<std::string> fileList {Utils::FileSystem::getDirContent(expandedDir, false)};
        for (auto& file : fileList) {
            if (Utils::FileSystem::getExtension(file) == mFileExtension) {
                if (Utils::FileSystem::isDirectory(file)) {
                    LOG(LogWarning) << "GuiGameImporter: Skipping \"" << file
                                    << "\" as it's a directory and not a file";
                    continue;
                }

                const long fileSize {Utils::FileSystem::getFileSize(file)};
                if (fileSize > MAX_FILE_SIZE) {
                    LOG(LogWarning) << "GuiGameImporter: File \"" << file << "\" is too big at "
                                    << fileSize << " bytes, skipping it";
                    continue;
                }

                if (Utils::FileSystem::getFileName(file) == "org.es_de.frontend.desktop")
                    continue;

                LOG(LogDebug)
                    << "GuiGameImporter::desktopshortcutRule(): Parsing desktop shortcut file \""
                    << file << "\"";

                bool validFile {false};
                bool noDisplay {false};
                std::string nameEntry;
                std::string execEntry;
                std::string categoriesEntry;
                std::ifstream desktopFileStream;

                desktopFileStream.open(file);

                for (std::string line; getline(desktopFileStream, line);) {
                    // Some non-standard .desktop files add a leading line such as
                    // "#!/usr/bin/env xdg-open" and some lines may also be indented by
                    // whitespace characters. So we need to handle such oddities in order
                    // to parse these files.
                    line = Utils::String::trim(line);
                    if (line.substr(0, 2) == "#!")
                        continue;
                    if (line.find("[Desktop Entry]") != std::string::npos)
                        validFile = true;
                    if (line.substr(0, 5) == "Name=")
                        nameEntry = line;
                    if (line.substr(0, 5) == "Exec=")
                        execEntry = line.substr(5, line.size() - 5);
                    if (line.substr(0, 11) == "Categories=")
                        categoriesEntry = line;
                    if (Utils::String::toLower(line).substr(0, 14) == "nodisplay=true")
                        noDisplay = true;
                }

                desktopFileStream.close();

                // Any .desktop file with a NoDisplay key set to true should be skipped as it's
                // not intended to be shown to the user.
                if (noDisplay) {
                    LOG(LogDebug) << "GuiGameImporter::desktopshortcutRule(): File has the "
                                     "NoDisplay key set to true, skipping it";
                    continue;
                }

                // If we're only importing games and the Categories flag does not contain a
                // "Game" string, then skip the entry.
                if (directory.gamesOnly &&
                    Utils::String::toLower(categoriesEntry).find("game") == std::string::npos) {
                    LOG(LogDebug) << "GuiGameImporter::desktopshortcutRule(): Set to only import "
                                     "games and the file is not categorized as a game, skipping it";
                    continue;
                }

                if (directory.filter != "") {
                    if (execEntry.empty()) {
                        LOG(LogDebug) << "GuiGameImporter::desktopshortcutRule(): An execFilter "
                                         "value has been defined but the file contains no Exec "
                                         "key, skipping it";
                        continue;
                    }
                    if (Utils::String::toLower(execEntry).find(
                            Utils::String::toLower(directory.filter)) == std::string::npos) {
                        LOG(LogDebug) << "GuiGameImporter::desktopshortcutRule(): File's Exec key "
                                         "does not match the defined execFilter value \""
                                      << directory.filter << "\", skipping it";
                        continue;
                    }
                }

                std::string targetFile;
                bool usedNameEntry {false};

                if (nameEntry != "") {
                    if (mStripSpecialChars->getState()) {
                        // Remove characters that are not allowed in filenames on FAT-based
                        // filesystems, which is also equivalent to what's not allowed on Windows.
                        nameEntry = Utils::String::replace(nameEntry, "\"", "");
                        nameEntry = Utils::String::replace(nameEntry, ":", "");
                        nameEntry = Utils::String::replace(nameEntry, "|", "");
                        nameEntry = Utils::String::replace(nameEntry, "/", "");
                        nameEntry = Utils::String::replace(nameEntry, "\\", "");
                        nameEntry = Utils::String::replace(nameEntry, "?", "");
                        nameEntry = Utils::String::replace(nameEntry, "*", "");
                        nameEntry = Utils::String::replace(nameEntry, "<", "");
                        nameEntry = Utils::String::replace(nameEntry, ">", "");
                    }
                    else {
                        // Always remove forward slashes and backslashes.
                        nameEntry = Utils::String::replace(nameEntry, "/", "");
                        nameEntry = Utils::String::replace(nameEntry, "\\", "");
                    }
                }

                if (validFile && nameEntry.length() > 5) {
                    targetFile = nameEntry.substr(5, nameEntry.length()) + ".desktop";
                    usedNameEntry = true;
                }
                else {
                    targetFile = file;
                }

                hasEntries = true;
                int index {1};

                std::string targetFileTemp {targetFile};

                // Add an index number to the filename in case there are multiple files with the
                // same name.
                while (Utils::FileSystem::exists(filesDir + "/" +
                                                 Utils::FileSystem::getFileName(targetFileTemp))) {
                    if (usedNameEntry) {
                        targetFileTemp = targetFile.substr(0, targetFile.length() - 8);
                        targetFileTemp.append(" (")
                            .append(std::to_string(index))
                            .append(").desktop");
                    }
                    else {
                        targetFileTemp = {Utils::FileSystem::getParent(file)};
                        targetFileTemp.append("/")
                            .append(
                                Utils::FileSystem::getStem(Utils::FileSystem::getFileName(file)))
                            .append(" (")
                            .append(std::to_string(index))
                            .append(")")
                            .append(Utils::FileSystem::getExtension(file));
                    }
                    ++index;
                }

                targetFile = targetFileTemp;

                if (usedNameEntry) {
                    LOG(LogDebug) << "GuiGameImporter::desktopshortcutRule(): Using Name entry "
                                     "from file to set filename to \""
                                  << targetFile << "\"";
                }
                else {
                    LOG(LogDebug) << "GuiGameImporter::desktopshortcutRule(): Couldn't read Name "
                                     "entry from file, falling back to using filename";
                }

                if (usedNameEntry)
                    Utils::FileSystem::copyFile(file, filesDir + "/" + targetFile, false);
                else
                    Utils::FileSystem::copyFile(
                        file, filesDir + "/" + Utils::FileSystem::getFileName(targetFile), false);
            }
        }
    }

    mHasEntries = hasEntries;
    mIsInventorying = false;
    mDoneInventorying = true;
}

bool GuiGameImporter::input(InputConfig* config, Input input)
{
    if (mIsInventorying)
        return true;

    if (config->isMappedTo("back", input))
        return true;

    if (GuiComponent::input(config, input))
        return true;

    if (!mSelectorWindow) {
        if (config->isMappedTo("y", input) && input.value != 0)
            pressedStart();

        if (input.value != 0 &&
            (config->isMappedTo("b", input) || config->isMappedTo("back", input))) {
            delete this;
            return true;
        }
    }
    else {
        if (input.value != 0 &&
            (config->isMappedTo("b", input) || config->isMappedTo("back", input))) {
            removeChild(mSelectorMenu.get());
            mainWindow();
            return true;
        }
    }

    return GuiComponent::input(config, input);
}
