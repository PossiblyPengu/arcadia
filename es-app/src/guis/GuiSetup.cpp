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
#include "guis/GuiEmulators.h"
#include "guis/GuiMenu.h"
#include "guis/GuiToolRunner.h"
#include "views/ViewController.h"
#include "utils/FileSystemUtil.h"
#include "utils/LocalizationUtil.h"
#include "utils/StringUtil.h"

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
        {"games", "get-started.sh", N_("Show me")},
        {"emulators", "install-emulators.sh", N_("Install")},
        {"controls", "setup-controls.sh", N_("Set up")},
        {"access", "grant-access.sh", N_("Allow")},
        {"saves", "connect-saves.sh", N_("Connect")},
        {"bios", "check-bios.sh", N_("Check")},
        {"deckhand", "get-deckhand.sh", N_("Get it")}};

    struct Tool {
        const char* label;
        const char* command;
    };
    const std::vector<Tool> sTools {{N_("Sort downloads"), "sort-roms.sh"},
                                    {N_("Sort inside folders"), "sort-roms.sh\" --deep \""},
                                    {N_("Undo the last sort"), "sort-roms.sh\" --undo \""},
                                    {N_("Emulators"), ""},
                                    {N_("Sync saves now"), "save-sync-now.sh"},
                                    {N_("Back up settings"), "backup.sh"},
                                    {N_("Restore a backup"), "backup.sh\" --restore \""},
                                    {N_("Update Arcadia"), "update-arcadia.sh"}};
    // The checklist's words. The setup tool sends each step as key|done|label|detail|code;values: the label and
    // detail are English, the code is turned into words here, so they can be translated. A step or code this version
    // doesn't know keeps the tool's English.
    std::string stepLabel(const std::string& key, const std::string& english)
    {
        static const std::vector<std::pair<const char*, const char*>> labels {
            {"games", N_("Games")},           {"emulators", N_("Emulators")},   {"controls", N_("Controls")},
            {"access", N_("Folder access")},  {"saves", N_("Cloud saves")},     {"bios", N_("BIOS files")},
            {"deckhand", N_("Windows games")}};
        for (const auto& [k, label] : labels) {
            if (key == k)
                return _(label);
        }
        return english;
    }

    std::string stepDetail(const std::string& key, const std::vector<std::string>& c, const std::string& english)
    {
        using Utils::String::format;
        const std::string what {c.empty() ? "" : c[0]};
        auto num = [&c](size_t i) { return i < c.size() ? std::atoi(c[i].c_str()) : 0; };
        auto arg = [&c](size_t i) { return i < c.size() ? c[i] : std::string {}; };
        if (key == "games" && what == "found") {
            std::string d {format(_n("%i game found", "%i games found", num(1)), num(1)) + " " +
                           format(_n("in %i console", "in %i consoles", num(2)), num(2))};
            if (c.size() > 3)
                d += ", " + format(_n("%i new one in Downloads", "%i new ones in Downloads", num(3)), num(3));
            return d;
        }
        if (key == "games" && what == "none")
            return format(_("none found in %s yet"), arg(1).c_str());
        if (key == "emulators") {
            if (what == "none")
                return _("add games first");
            if (what == "installed")
                return format(_n("%i installed", "%i installed", num(1)), num(1));
            if (what == "ready")
                return _("ready for all your games");
            if (what == "cores")
                return _("cores missing");
            if (what == "needs")
                return format(_("needs %s"), arg(1).c_str());
        }
        if (key == "controls") {
            if (what == "set" && c.size() > 1)
                return format(_("set up for %s"), arg(1).c_str());
            if (what == "set")
                return _("set up");
            if (what == "setmany")
                return format(_("set up for %s and %s"), arg(1).c_str(), arg(2).c_str());
            if (what == "todo")
                return _("not set up yet");
        }
        if (key == "access" && (what == "yes" || what == "no"))
            return what == "yes" ? _("emulators can see your games") : _("emulators can't see your games yet");
        if (key == "saves" && (what == "on" || what == "off"))
            return what == "on" ? _("syncing to Google Drive") : _("not connected yet");
        if (key == "bios" && what == "ok")
            return _("all the ones needed are there");
        if (key == "bios" && what == "missing")
            return format(_n("%i missing", "%i missing", num(1)), num(1));
        if (key == "deckhand" && (what == "yes" || what == "no"))
            return what == "yes" ? _("Deckhand is installed") : _("not installed yet: Arcadia's sister app");
        return english;
    }
} // namespace

GuiSetup::GuiSetup(const std::string& toolsDirectory)
    : mRenderer {Renderer::getInstance()}
    , mToolsDirectory {toolsDirectory}
    , mColumn {0}
    , mShared {std::make_shared<Shared>()}
{

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
    mHeadline.setText(_("Setup"));
    addChild(&mHeadline);
    mSubline.setFont(Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT));
    mSubline.setAutoCalcExtent(glm::ivec2 {0, 1});
    mHeadline.setAutoCalcExtent(glm::ivec2 {0, 1});
    mSubline.setColor(mMenuColorSecondary);
    mSubline.setText(_("Checking what's ready…"));
    addChild(&mSubline);
    mToolsTitle.setFont(Font::get(FONT_SIZE_LARGE * 0.74f, FONT_PATH_TITLE));
    mToolsTitle.setColor(mMenuColorTitle);
    mToolsTitle.setText(_("Tools"));
    addChild(&mToolsTitle);

    mSteps = std::make_shared<ComponentList>();
    mTools = std::make_shared<ComponentList>();
    for (const Tool& tool : sTools) {
        ComponentListRow row;
        row.addElement(std::make_shared<TextComponent>(_(tool.label), Font::get(FONT_SIZE_MEDIUM),
                                                       mMenuColorPrimary),
                       true);
        const std::string title {_(tool.label)};
        const std::string command {"\"" + mToolsDirectory + "/" + tool.command + "\""};
        if (std::string {tool.command}.empty())
            row.makeAcceptInputHandler([this] { openEmulators(); });
        else
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
    // (Nothing to wait for: a status read still running has its own reference to what it shares with this screen.)
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
    if (mShared->reading)
        return;
    mShared->reading = true;
    // Everything the thread needs is worked out here: it touches nothing of this screen, which may be gone by then.
    const std::string cmd {"ARCADIA_OUTPUT=stdout ARCADIA_HOME=\"" + Utils::FileSystem::getAppDataDirectory() +
                           "\" ARCADIA_ROMS=\"" + FileData::getROMDirectory() + "\" bash \"" + mToolsDirectory +
                           "/get-started.sh\" --status 2>/dev/null"};
    std::thread([shared = mShared, cmd] {
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
            if (fields.size() >= 4) {
                std::vector<std::string> code;
                if (fields.size() >= 5) {
                    std::istringstream codeParts {fields[4]};
                    std::string value;
                    while (std::getline(codeParts, value, ';'))
                        code.push_back(value);
                }
                steps.push_back({fields[0], fields[1] != "0", fields[2], fields[3], code});
            }
        }
        {
            std::unique_lock<std::mutex> lock {shared->mutex};
            shared->status = steps;
        }
        shared->reading = false;
        shared->ready = true;
    }).detach();
}

void GuiSetup::showStatus()
{
    std::vector<Step> steps;
    {
        std::unique_lock<std::mutex> lock {mShared->mutex};
        steps = mShared->status;
    }

    const int cursor {mSteps->getCursorId()};
    mSteps = std::make_shared<ComponentList>();
    const std::shared_ptr<Font> font {Font::get(FONT_SIZE_MEDIUM)};
    const std::shared_ptr<Font> quiet {Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT)};
    int total {0};
    int done {0};
    int newGames {0};

    for (const Step& step : steps) {
        if (step.key == "games") {
            // A tool changed what's in the ROM folders (a sort, an undo): the consoles are looked through again once
            // Settings closes, so the games are there (and the welcome screen goes) without starting Arcadia again.
            const int count {step.done ? std::atoi(step.detail.c_str()) : 0};
            if (mGameCount >= 0 && count != mGameCount)
                ViewController::getInstance()->requestRescan();
            mGameCount = count;
        }
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
        auto label = std::make_shared<TextComponent>(stepLabel(step.key, step.label), font, mMenuColorPrimary);
        std::shared_ptr<TextComponent> todo;
        if (!step.done)
            todo = std::make_shared<TextComponent>("  " + _(action->todo),
                                                   Font::get(FONT_SIZE_SMALL), mMenuColorAccentInk,
                                                   ALIGN_RIGHT);
        // The detail gets whatever room the row has left, and is shortened with an ellipsis to fit.
        const float room {mSteps->getSize().x -
                          std::round(56.0f * mRenderer->getScreenWidthModifier()) -
                          icon->getSize().x - spacer->getSize().x - label->getSize().x -
                          (todo ? todo->getSize().x : 0.0f) - font->getLetterHeight()};
        row.addElement(label, false);
        auto detail = std::make_shared<TextComponent>("", quiet, mMenuColorSecondary, ALIGN_LEFT);
        detail->setText("  ·  " + stepDetail(step.key, step.code, step.detail), true, std::max(room, 0.0f));
        row.addElement(detail, true);
        if (todo)
            row.addElement(todo, false);

        const std::string title {stepLabel(step.key, step.label)};
        const std::string command {"\"" + mToolsDirectory + "/" + action->tool + "\""};
        if (step.key == "emulators")
            row.makeAcceptInputHandler([this] { openEmulators(); });
        else
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
        mHeadline.setText(_("Setup"));
        mSubline.setText(_("The checklist couldn't be read. The tools on the right still work."));
    }
    else if (left == 0) {
        mHeadline.setText(_("All set"));
        mSubline.setText(_("Everything is ready. Have fun."));
    }
    else {
        mHeadline.setText(done == 0 ? _("Let's get you set up") : _("Almost ready"));
        mSubline.setText(Utils::String::format(_n("One thing left to do.", "%i things left to do.", left), left));
    }
    setFocusColumn(mColumn);
    updateHelpPrompts();
}

void GuiSetup::runTool(const std::string& title, const std::string& command)
{
    mWindow->pushGui(new GuiToolRunner(title, command, [this] { readStatus(); }));
}

void GuiSetup::openEmulators()
{
    mWindow->pushGui(new GuiEmulators(mToolsDirectory, [this] { readStatus(); }));
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
    if (mShared->ready) {
        mShared->ready = false;
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
    if (input.value != 0 && config->isMappedTo("left", input) && mColumn == 1) {
        setFocusColumn(0);
        return true;
    }
    if (input.value != 0 && config->isMappedTo("left", input) && mColumn == 0) {
        delete this; // (left of the checklist is the settings rail: the same as B)
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
    return prompts;
}
