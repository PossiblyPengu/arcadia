//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiSetup.cpp
//

#include "guis/GuiSetup.h"

#include "FileData.h"
#include "Log.h"
#include "Window.h"
#include "components/MenuComponent.h"
#include "guis/GuiMenu.h"
#include "guis/GuiToolRunner.h"
#include "utils/FileSystemUtil.h"
#include "utils/LocalizationUtil.h"

#include <array>
#include <cstdio>
#include <sstream>

namespace
{
    // What choosing a checklist step does: the tool it runs and the word shown while it isn't done.
    struct StepAction {
        const char* key;
        const char* tool;
        const char* todo;
    };
    const std::vector<StepAction> sStepActions {
        {"games", "get-started.sh", "Where do they go?"},
        {"emulators", "install-emulators.sh", "Install"},
        {"controls", "setup-controls.sh", "Set up"},
        {"access", "grant-access.sh", "Allow"},
        {"saves", "get-started.sh", "How to connect"},
        {"bios", "check-bios.sh", "See which"},
        {"deckhand", "get-deckhand.sh", "Get Deckhand"}};

    struct Tool {
        const char* label;
        const char* command;
    };
    const std::vector<Tool> sTools {{"Sort downloads", "sort-roms.sh"},
                                    {"Sort downloads and subfolders", "sort-roms.sh\" --deep \""},
                                    {"Undo the last sort", "sort-roms.sh\" --undo \""},
                                    {"Update emulators", "update-emulators.sh"},
                                    {"Sync saves now", "save-sync-now.sh"},
                                    {"Back up settings", "backup.sh"},
                                    {"Restore the latest backup", "backup.sh\" --restore \""},
                                    {"Update Arcadia", "update-arcadia.sh"}};
} // namespace

GuiSetup::GuiSetup(const std::string& toolsDirectory)
    : mRenderer {Renderer::getInstance()}
    , mToolsDirectory {toolsDirectory}
    , mColumn {0}
    , mRailSection {false}
    , mReading {false}
    , mStatusReady {false}
{
    mRailSection = GuiMenu::sRail != nullptr && mWindow->peekGui() == GuiMenu::sRail;

    mStepsCard.setFrameColor(mMenuColorFrame);
    mToolsCard.setFrameColor(mMenuColorFrame);
    addChild(&mStepsCard);
    addChild(&mToolsCard);

    mRing.setImage(":/graphics/setup/ring_0.svg");
    addChild(&mRing);
    mCount.setFont(Font::get(FONT_SIZE_MEDIUM, FONT_PATH_BOLD));
    mCount.setColor(mMenuColorPrimary);
    mCount.setAutoCalcExtent(glm::ivec2 {0, 0});
    mCount.setHorizontalAlignment(ALIGN_CENTER);
    mCount.setVerticalAlignment(ALIGN_CENTER);
    addChild(&mCount);
    mHeadline.setFont(Font::get(FONT_SIZE_LARGE * 0.8f, FONT_PATH_TITLE));
    mHeadline.setColor(mMenuColorTitle);
    mHeadline.setText("Setup");
    addChild(&mHeadline);
    mSubline.setFont(Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT));
    mSubline.setAutoCalcExtent(glm::ivec2 {0, 1});
    mHeadline.setAutoCalcExtent(glm::ivec2 {0, 1});
    mSubline.setColor(mMenuColorSecondary);
    mSubline.setText("Checking what's ready…");
    addChild(&mSubline);
    mToolsTitle.setFont(Font::get(FONT_SIZE_LARGE * 0.74f, FONT_PATH_TITLE));
    mToolsTitle.setColor(mMenuColorTitle);
    mToolsTitle.setText("Tools");
    addChild(&mToolsTitle);

    mSteps = std::make_shared<ComponentList>();
    mTools = std::make_shared<ComponentList>();
    for (const Tool& tool : sTools) {
        ComponentListRow row;
        row.addElement(std::make_shared<TextComponent>(tool.label, Font::get(FONT_SIZE_MEDIUM),
                                                       mMenuColorPrimary),
                       true);
        const std::string title {tool.label};
        const std::string command {"\"" + mToolsDirectory + "/" + tool.command + "\""};
        row.makeAcceptInputHandler([this, title, command] { runTool(title, command); });
        mTools->addRow(row);
    }

    // The settings rail's card area, or most of the screen when Setup is opened on its own.
    const glm::vec3 pos {MenuComponent::sheetPosition()};
    const glm::vec2 margin {MenuComponent::sheetMargin()};
    setPosition(pos);
    setSize(mRenderer->getScreenWidth() - pos.x - margin.x,
            mRenderer->getScreenHeight() * 0.9f - pos.y);
    layout();
    setFocusColumn(0);
    readStatus();
}

GuiSetup::~GuiSetup()
{
    if (mThread && mThread->joinable())
        mThread->join();
}

void GuiSetup::layout()
{
    const float gap {std::round(mRenderer->getScreenWidth() * 0.018f)};
    const float pad {std::round(mRenderer->getScreenWidth() * 0.02f)};
    const float leftWidth {std::round((mSize.x - gap) * 0.6f)};
    const float rightWidth {mSize.x - gap - leftWidth};

    mStepsCard.fitTo({leftWidth, mSize.y});
    mToolsCard.fitTo({rightWidth, mSize.y}, {leftWidth + gap, 0.0f, 0.0f});

    const float ringSize {std::round(mRenderer->getScreenHeight() * 0.1f)};
    mRing.setResize(ringSize, ringSize);
    mRing.setPosition(pad, pad);
    mCount.setSize(ringSize, ringSize);
    mCount.setPosition(pad, pad);

    const float textX {pad * 1.6f + ringSize};
    mHeadline.setSize(leftWidth - textX - pad, 0.0f);
    mHeadline.setPosition(textX, pad + ringSize * 0.5f - mHeadline.getFont()->getHeight());
    mSubline.setSize(leftWidth - textX - pad, 0.0f);
    mSubline.setPosition(textX, pad + ringSize * 0.52f);

    const float listTop {pad * 1.6f + ringSize};
    const float inset {std::round(mRenderer->getScreenWidth() * 0.012f)};
    mSteps->setPosition(inset, listTop);
    mSteps->setSize(leftWidth - inset * 2.0f, mSize.y - listTop - inset);

    mToolsTitle.setSize(rightWidth - pad * 2.0f, 0.0f);
    mToolsTitle.setPosition(leftWidth + gap + pad, pad);
    const float toolsTop {pad * 1.6f + mToolsTitle.getFont()->getHeight()};
    mTools->setPosition(leftWidth + gap + inset, toolsTop);
    mTools->setSize(rightWidth - inset * 2.0f, mSize.y - toolsTop - inset);
}

void GuiSetup::readStatus()
{
    if (mReading)
        return;
    if (mThread && mThread->joinable())
        mThread->join();
    mReading = true;
    mThread = std::make_unique<std::thread>([this] {
        const std::string cmd {"ARCADIA_OUTPUT=stdout ARCADIA_HOME=\"" +
                               Utils::FileSystem::getAppDataDirectory() + "\" ARCADIA_ROMS=\"" +
                               FileData::getROMDirectory() + "\" bash \"" + mToolsDirectory +
                               "/get-started.sh\" --status 2>/dev/null"};
        std::string output;
        if (FILE* pipe = popen(cmd.c_str(), "r")) {
            std::array<char, 512> buffer {};
            while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr)
                output += buffer.data();
            pclose(pipe);
        }
        std::vector<Step> steps;
        std::istringstream lines {output};
        std::string line;
        while (std::getline(lines, line)) {
            std::vector<std::string> fields;
            std::istringstream parts {line};
            std::string field;
            while (std::getline(parts, field, '|'))
                fields.push_back(field);
            if (fields.size() >= 4)
                steps.push_back({fields[0], fields[1] != "0", fields[2], fields[3]});
        }
        {
            std::unique_lock<std::mutex> lock {mMutex};
            mStatus = steps;
        }
        mReading = false;
        mStatusReady = true;
    });
}

void GuiSetup::showStatus()
{
    std::vector<Step> steps;
    {
        std::unique_lock<std::mutex> lock {mMutex};
        steps = mStatus;
    }

    const int cursor {mSteps->getCursorId()};
    mSteps = std::make_shared<ComponentList>();
    const std::shared_ptr<Font> font {Font::get(FONT_SIZE_MEDIUM)};
    const std::shared_ptr<Font> quiet {Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT)};
    int total {0};
    int done {0};
    int newGames {0};

    for (const Step& step : steps) {
        if (step.key == "inbox") {
            newGames = std::atoi(step.done ? step.label.c_str() : "0");
            continue;
        }
        auto action = std::find_if(sStepActions.cbegin(), sStepActions.cend(),
                                   [&step](const StepAction& a) { return step.key == a.key; });
        if (action == sStepActions.cend())
            continue;
        ++total;
        if (step.done)
            ++done;

        ComponentListRow row;
        auto icon = std::make_shared<ImageComponent>();
        icon->setResize(0.0f, std::round(font->getLetterHeight() * 1.6f));
        icon->setImage(step.done ? ":/graphics/setup/done.svg" : ":/graphics/setup/todo.svg");
        icon->setColorShift(step.done ? mMenuColorGreen : mMenuColorScrollIndicators);
        row.addElement(icon, false);
        auto spacer = std::make_shared<GuiComponent>();
        spacer->setSize(std::round(font->getLetterHeight() * 0.8f), 0.0f);
        row.addElement(spacer, false);
        auto label = std::make_shared<TextComponent>(step.label, font, mMenuColorPrimary);
        std::shared_ptr<TextComponent> todo;
        if (!step.done)
            todo = std::make_shared<TextComponent>("  " + std::string {action->todo},
                                                   Font::get(FONT_SIZE_SMALL), mMenuColorAccentInk,
                                                   ALIGN_RIGHT);
        // The detail gets whatever room the row has left, and is shortened with an ellipsis to fit.
        const float room {mSteps->getSize().x -
                          std::round(56.0f * mRenderer->getScreenWidthModifier()) -
                          icon->getSize().x - spacer->getSize().x - label->getSize().x -
                          (todo ? todo->getSize().x : 0.0f) - font->getLetterHeight()};
        row.addElement(label, false);
        auto detail = std::make_shared<TextComponent>("", quiet, mMenuColorSecondary, ALIGN_LEFT);
        detail->setText("  ·  " + step.detail, true, std::max(room, 0.0f));
        row.addElement(detail, true);
        if (todo)
            row.addElement(todo, false);

        const std::string title {step.label};
        const std::string command {"\"" + mToolsDirectory + "/" + action->tool + "\""};
        row.makeAcceptInputHandler([this, title, command] { runTool(title, command); });
        mSteps->addRow(row);
    }
    (void)newGames;
    layout();
    if (cursor > 0)
        mSteps->moveCursor(std::min(cursor, static_cast<int>(mSteps->size()) - 1));

    const int left {total - done};
    mRing.setImage(":/graphics/setup/ring_" + std::to_string(std::clamp(done * 6 / std::max(total, 1), 0, 6)) +
                   ".svg");
    mCount.setText(std::to_string(done) + "/" + std::to_string(total));
    if (total == 0) {
        mHeadline.setText("Setup");
        mSubline.setText("The checklist couldn't be read. The tools on the right still work.");
    }
    else if (left == 0) {
        mHeadline.setText("All set");
        mSubline.setText("Everything is ready. Have fun.");
    }
    else {
        mHeadline.setText(done == 0 ? "Let's get you set up" : "Almost ready");
        const std::vector<std::string> counts {"One thing", "Two things", "Three things",
                                               "Four things", "Five things", "Six things",
                                               "Seven things"};
        mSubline.setText((left <= 7 ? counts.at(left - 1) : std::to_string(left) + " things") +
                         " left to do.");
    }
    setFocusColumn(mColumn);
    updateHelpPrompts();
}

void GuiSetup::runTool(const std::string& title, const std::string& command)
{
    mWindow->pushGui(new GuiToolRunner(title, command, [this] { readStatus(); }));
}

void GuiSetup::setFocusColumn(int column)
{
    mColumn = column;
    if (mColumn == 0) {
        mTools->onFocusLost();
        mSteps->onFocusGained();
    }
    else {
        mSteps->onFocusLost();
        mTools->onFocusGained();
    }
}

void GuiSetup::update(int deltaTime)
{
    if (mStatusReady) {
        mStatusReady = false;
        showStatus();
    }
    mSteps->update(deltaTime);
    mTools->update(deltaTime);
    GuiComponent::update(deltaTime);
}

void GuiSetup::render(const glm::mat4& parentTrans)
{
    const glm::mat4 trans {parentTrans * getTransform()};
    renderChildren(trans);
    mSteps->render(trans);
    mTools->render(trans);
}

bool GuiSetup::input(InputConfig* config, Input input)
{
    if (input.value != 0 && config->isMappedTo("b", input)) {
        delete this;
        return true;
    }
    if (mRailSection && input.value != 0 &&
        (config->isMappedTo("leftshoulder", input) || config->isMappedTo("rightshoulder", input))) {
        const int direction {config->isMappedTo("leftshoulder", input) ? -1 : 1};
        delete this;
        if (GuiMenu::sRail != nullptr)
            GuiMenu::sRail->stepSection(direction);
        return true;
    }
    if (input.value != 0 && config->isMappedTo("left", input) && mColumn == 1) {
        setFocusColumn(0);
        return true;
    }
    if (input.value != 0 && config->isMappedTo("right", input) && mColumn == 0) {
        setFocusColumn(1);
        return true;
    }
    return focusedList()->input(config, input);
}

std::vector<HelpPrompt> GuiSetup::getHelpPrompts()
{
    std::vector<HelpPrompt> prompts;
    prompts.push_back(HelpPrompt("up/down", _("choose")));
    prompts.push_back(HelpPrompt("left/right", _("switch side")));
    prompts.push_back(HelpPrompt("a", _("do it")));
    prompts.push_back(HelpPrompt("b", _("back")));
    if (mRailSection)
        prompts.push_back(HelpPrompt("lr", _("sections")));
    return prompts;
}
