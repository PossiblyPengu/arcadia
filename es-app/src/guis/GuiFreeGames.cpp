//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiFreeGames.cpp
//

#include "guis/GuiFreeGames.h"

#include "SystemData.h"
#include "Window.h"
#include "components/ImageComponent.h"
#include "components/MenuComponent.h"
#include "guis/GuiMsgBox.h"
#include "guis/GuiToolRunner.h"
#include "utils/LocalizationUtil.h"
#include "views/ViewController.h"

#include <map>
#include <sstream>

GuiFreeGames::GuiFreeGames(const std::string& toolsDirectory, std::function<void()> onClose)
    : mRenderer {Renderer::getInstance()}
    , mToolsDirectory {toolsDirectory}
    , mOnClose {onClose}
    , mConsoleCursor {0}
    , mInstalledAtStart {-1}
    , mLoaded {false}
    , mGotSomething {false}
{
    mCard.setFrameColor(mMenuColorFrame);
    addChild(&mCard);
    mHeadline.setFont(Font::get(FONT_SIZE_LARGE * 0.8f, FONT_PATH_TITLE));
    mHeadline.setColor(mMenuColorTitle);
    mHeadline.setAutoCalcExtent(glm::ivec2 {0, 1});
    mHeadline.setText("Free games");
    addChild(&mHeadline);
    mSubline.setFont(Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT));
    mSubline.setColor(mMenuColorSecondary);
    mSubline.setAutoCalcExtent(glm::ivec2 {0, 1});
    mSubline.setText("Fetching the list of free games…");
    addChild(&mSubline);
    mList = std::make_shared<ComponentList>();

    const glm::vec3 pos {MenuComponent::sheetPosition()};
    const glm::vec2 margin {MenuComponent::sheetMargin()};
    setPosition(pos);
    setSize(mRenderer->getScreenWidth() - pos.x - margin.x, mRenderer->getScreenHeight() * 0.9f - pos.y);
    layout();
    readList();
}

GuiFreeGames::~GuiFreeGames() = default;

void GuiFreeGames::layout()
{
    const float pad {std::round(mRenderer->getScreenWidth() * 0.02f)};
    const float inset {std::round(mRenderer->getScreenWidth() * 0.012f)};
    mCard.fitTo(mSize);
    mHeadline.setSize(mSize.x - pad * 2.0f, 0.0f);
    mHeadline.setPosition(pad, pad);
    mSubline.setSize(mSize.x - pad * 2.0f, 0.0f);
    mSubline.setPosition(pad, pad + mHeadline.getFont()->getHeight() * 1.05f);
    const float top {pad * 1.4f + mHeadline.getFont()->getHeight() * 1.05f + mSubline.getFont()->getHeight()};
    mList->setPosition(inset, top);
    mList->setSize(mSize.x - inset * 2.0f, mSize.y - top - inset);
}

void GuiFreeGames::readList(bool refresh)
{
    // A new shared state each time: a read still running from before writes only into its own.
    mShared = std::make_shared<Shared>();
    const std::string command {GuiToolRunner::toolEnvironment() + "bash \"" + mToolsDirectory +
                               "/free-games.sh\" " + (refresh ? "--refresh" : "--list")};
    std::thread([shared = mShared, command] {
        std::string output;
        int code {1};
        GuiToolRunner::runWithoutPreload(command, [&output](const std::string& chunk) { output += chunk; }, &code);
        std::vector<Game> games;
        std::istringstream lines {output};
        std::string line;
        std::string error;
        while (std::getline(lines, line)) {
            std::vector<std::string> f;
            std::istringstream parts {line};
            std::string field;
            while (std::getline(parts, field, '|'))
                f.push_back(field);
            if (f.size() >= 7 && f[0] == "game")
                games.push_back({f[1], f[2], f[3], f[4], f[5], f[6] == "1", f.size() > 7 ? f[7] : ""});
            else if (line.rfind("✗", 0) == 0)
                error = line.substr(std::string {"✗ "}.size());
        }
        std::unique_lock<std::mutex> lock {shared->mutex};
        shared->games = games;
        shared->error = games.empty() ? (error.empty() ? "The list couldn't be read." : error) : "";
        shared->done = true;
    }).detach();
}

int GuiFreeGames::installedCount() const
{
    int n {0};
    for (const Game& g : mGames)
        n += g.installed ? 1 : 0;
    return n;
}

void GuiFreeGames::newList()
{
    // The list being replaced may be the one whose row was just chosen (this runs inside its input handler): it's
    // kept until the next update, so it isn't freed under its own feet.
    mRetiredLists.push_back(mList);
    mList = std::make_shared<ComponentList>();
    layout();
}

void GuiFreeGames::showConsoles()
{
    mSystem.clear();
    newList();
    const std::shared_ptr<Font> font {Font::get(FONT_SIZE_MEDIUM)};
    const std::shared_ptr<Font> quiet {Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT)};
    // The consoles in the order the list gives them (most games first), with how many and how many you have.
    std::vector<std::string> order;
    std::map<std::string, std::pair<std::string, std::pair<int, int>>> counts;
    for (const Game& g : mGames) {
        if (counts.find(g.system) == counts.end()) {
            order.push_back(g.system);
            counts[g.system] = {g.console, {0, 0}};
        }
        counts[g.system].second.first += 1;
        counts[g.system].second.second += g.installed ? 1 : 0;
    }
    for (const std::string& system : order) {
        const auto& [console, n] {counts[system]};
        ComponentListRow row;
        row.addElement(std::make_shared<TextComponent>(console, font, mMenuColorPrimary), true);
        std::string detail {std::to_string(n.first) + (n.first == 1 ? " game" : " games")};
        if (n.second > 0)
            detail += " · " + std::to_string(n.second) + " added";
        row.addElement(std::make_shared<TextComponent>(detail + "  ", quiet, mMenuColorSecondary), false);
        auto arrow = std::make_shared<ImageComponent>();
        arrow->setResize(0.0f, font->getLetterHeight());
        arrow->setImage(":/graphics/arrow.svg");
        arrow->setColorShift(mMenuColorPrimary);
        row.addElement(arrow, false);
        row.makeAcceptInputHandler([this, system] { showGames(system); });
        mList->addRow(row);
    }
    layout();
    if (mConsoleCursor > 0 && mList->size() > 0)
        mList->moveCursor(std::min(mConsoleCursor, static_cast<int>(mList->size()) - 1));
    mList->onFocusGained();
    mHeadline.setText("Free games");
    mSubline.setText(mGames.empty() ?
                         "No free games could be listed. Check the Deck is online, then open this again." :
                         "Homebrew and freeware, free to play and share. Pick a console, then a game.");
    updateHelpPrompts();
}

void GuiFreeGames::showGames(const std::string system)
{
    // (system is a copy: the row it came from goes with the old list.)
    if (mSystem.empty())
        mConsoleCursor = mList->getCursorId(); // (to come back to the same console)
    mSystem = system;
    newList();
    const std::shared_ptr<Font> font {Font::get(FONT_SIZE_MEDIUM)};
    const std::shared_ptr<Font> small {Font::get(FONT_SIZE_SMALL)};
    const std::shared_ptr<Font> quiet {Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT)};
    std::string console;
    int count {0};
    for (const Game& g : mGames) {
        if (g.system != system)
            continue;
        console = g.console;
        ++count;
        ComponentListRow row;
        auto tag = std::make_shared<TextComponent>(g.installed ? "  Added" : "  Get", small,
                                                   g.installed ? mMenuColorSecondary : mMenuColorAccentInk,
                                                   ALIGN_RIGHT);
        // The name gets most of the row (a long one is shortened), the details what's left, and the tag always fits.
        const float width {mList->getSize().x - std::round(56.0f * mRenderer->getScreenWidthModifier()) -
                           tag->getSize().x};
        auto label = std::make_shared<TextComponent>("", font, mMenuColorPrimary);
        label->setText(g.title, true, width * 0.7f);
        const float room {width - label->getSize().x - font->getLetterHeight()};
        row.addElement(label, false);
        std::string detail {g.by.empty() ? g.blurb : g.blurb.empty() ? "by " + g.by : g.by + " · " + g.blurb};
        auto detailText = std::make_shared<TextComponent>("", quiet, mMenuColorSecondary, ALIGN_LEFT);
        detailText->setText(detail.empty() ? "" : "  ·  " + detail, true, std::max(room, 0.0f));
        row.addElement(detailText, true);
        row.addElement(tag, false);
        const Game copy {g};
        row.makeAcceptInputHandler([this, copy] { choose(copy); });
        mList->addRow(row);
    }
    layout();
    mList->onFocusGained();
    mHeadline.setText(console);
    mSubline.setText(std::to_string(count) + (count == 1 ? " free game" : " free games") +
                     ". A shows what a game is and gets it; B goes back to the consoles.");
    updateHelpPrompts();
}

void GuiFreeGames::choose(const Game& game)
{
    // What it is, from the list's own details, then Get (or just Close when you have it).
    std::string about;
    GuiToolRunner::runWithoutPreload(GuiToolRunner::toolEnvironment() + "bash \"" + mToolsDirectory +
                                         "/free-games.sh\" --about \"" + game.id + "\"",
                                     [&about](const std::string& chunk) { about += chunk; });
    while (!about.empty() && (about.back() == '\n' || about.back() == ' '))
        about.pop_back();
    // (The first line is the name: as its own sentence it becomes the dialog's title.)
    const size_t eol {about.find('\n')};
    if (eol != std::string::npos)
        about = about.substr(0, eol) + ".\n" + about.substr(eol + 1);
    if (about.empty())
        about = game.title + ".";
    if (game.installed) {
        mWindow->pushGui(new GuiMsgBox(about + "\n\nYou have it: it's under " + game.console + ".", _("CLOSE"),
                                       nullptr));
        return;
    }
    const Game copy {game};
    mWindow->pushGui(new GuiMsgBox(about, _("GET IT"), [this, copy] { get(copy); }, _("CANCEL"), nullptr));
}

void GuiFreeGames::get(const Game& game)
{
    mLastGot = game.system;
    mWindow->pushGui(new GuiToolRunner("Getting " + game.title,
                                       "bash \"" + mToolsDirectory + "/free-games.sh\" --install \"" + game.id + "\"",
                                       [this] { readList(); }));
}

void GuiFreeGames::back()
{
    if (!mSystem.empty()) {
        showConsoles();
        return;
    }
    finish();
}

void GuiFreeGames::finish()
{
    if (!mGotSomething) {
        auto onClose = mOnClose;
        delete this;
        if (onClose)
            onClose();
        return;
    }
    // Something was added: close Settings and rescan, so the new games are there (and the welcome screen goes, if
    // these are the first ones), then show the console of the last one.
    Window* window {mWindow};
    const std::string lastGot {mLastGot};
    while (window->peekGui() != nullptr && window->peekGui() != ViewController::getInstance())
        delete window->peekGui(); // (this screen too)
    ViewController::getInstance()->rescanROMDirectory();
    const std::string alias {lastGot == "genesis" ? "megadrive" : lastGot == "megadrive" ? "genesis" : ""};
    ViewController* view {ViewController::getInstance()};
    if (view->getState().viewing != ViewController::ViewMode::SYSTEM_SELECT)
        return; // (started in a game list: left as it is)
    for (SystemData* system : SystemData::sSystemVector) {
        if (system->getName() == lastGot || (!alias.empty() && system->getName() == alias)) {
            view->goToSystemView(system, false);
            break;
        }
    }
}

void GuiFreeGames::update(int deltaTime)
{
    mRetiredLists.clear();
    if (mShared && mShared->done) {
        std::vector<Game> games;
        std::string error;
        {
            std::unique_lock<std::mutex> lock {mShared->mutex};
            games = mShared->games;
            error = mShared->error;
        }
        mShared.reset();
        mGames = games;
        const int installed {installedCount()};
        if (mInstalledAtStart < 0)
            mInstalledAtStart = installed;
        else if (installed > mInstalledAtStart)
            mGotSomething = true;
        if (!mLoaded || mSystem.empty()) {
            showConsoles();
        }
        else {
            const int cursor {mList->getCursorId()};
            showGames(mSystem);
            if (cursor > 0 && mList->size() > 0)
                mList->moveCursor(std::min(cursor, static_cast<int>(mList->size()) - 1));
        }
        mLoaded = true;
        if (!error.empty() && mGames.empty())
            mSubline.setText(error + " Check the Deck is online, then press Y to try again.");
    }
    mList->update(deltaTime);
    GuiComponent::update(deltaTime);
}

void GuiFreeGames::render(const glm::mat4& parentTrans)
{
    const glm::mat4 trans {parentTrans * getTransform()};
    renderChildren(trans);
    mList->render(trans);
}

bool GuiFreeGames::input(InputConfig* config, Input input)
{
    if (input.value != 0 && config->isMappedTo("b", input)) {
        back();
        return true;
    }
    if (input.value != 0 && config->isMappedTo("y", input) && mSystem.empty() && mLoaded) {
        mLoaded = false;
        mSubline.setText("Fetching the list of free games again…");
        readList(true);
        return true;
    }
    return mList->input(config, input);
}

std::vector<HelpPrompt> GuiFreeGames::getHelpPrompts()
{
    std::vector<HelpPrompt> prompts;
    prompts.push_back(HelpPrompt("up/down", _("choose")));
    prompts.push_back(HelpPrompt("a", mSystem.empty() ? _("open") : _("details")));
    if (mSystem.empty())
        prompts.push_back(HelpPrompt("y", _("refresh the list")));
    prompts.push_back(HelpPrompt("b", mSystem.empty() ? (mGotSomething ? _("done") : _("back")) : _("consoles")));
    return prompts;
}
