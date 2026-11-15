//  SPDX-License-Identifier: MIT
//
//  Arcadia
//  GuiEmulators.cpp
//

#include "guis/GuiEmulators.h"

#include "Window.h"
#include "components/ImageComponent.h"
#include "components/MenuComponent.h"
#include "guis/GuiMsgBox.h"
#include "guis/GuiToolRunner.h"
#include "utils/LocalizationUtil.h"
#include "utils/StringUtil.h"

#include <sstream>

GuiEmulators::GuiEmulators(const std::string& toolsDirectory, std::function<void()> onClose)
    : mRenderer {Renderer::getInstance()}
    , mToolsDirectory {toolsDirectory}
    , mOnClose {onClose}
    , mShared {std::make_shared<Shared>()}
{
    mCard.setFrameColor(mMenuColorFrame);
    addChild(&mCard);
    mHeadline.setFont(Font::get(FONT_SIZE_LARGE * 0.8f, FONT_PATH_TITLE));
    mHeadline.setColor(mMenuColorTitle);
    mHeadline.setAutoCalcExtent(glm::ivec2 {0, 1});
    mHeadline.setText(_("Emulators"));
    addChild(&mHeadline);
    mSubline.setFont(Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT));
    mSubline.setColor(mMenuColorSecondary);
    mSubline.setAutoCalcExtent(glm::ivec2 {0, 1});
    mSubline.setText(_("Looking at your games…"));
    addChild(&mSubline);
    mList = std::make_shared<ComponentList>();

    // Where Setup is (the settings rail's card area), so it reads as a page of Setup.
    const glm::vec3 pos {MenuComponent::sheetPosition()};
    const glm::vec2 margin {MenuComponent::sheetMargin()};
    setPosition(pos);
    setSize(mRenderer->getScreenWidth() - pos.x - margin.x, mRenderer->getScreenHeight() * 0.9f - pos.y);
    layout();
    readPlan();
}

GuiEmulators::~GuiEmulators()
{
    // (Nothing to wait for: a plan read still running has its own reference to what it shares with this screen.)
}

void GuiEmulators::layout()
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

void GuiEmulators::readPlan()
{
    if (mShared->reading)
        return;
    mShared->reading = true;
    const std::string cmd {GuiToolRunner::toolEnvironment() + "bash \"" + mToolsDirectory +
                           "/install-emulators.sh\" --plan"};
    std::thread([shared = mShared, cmd] {
        std::string output;
        GuiToolRunner::runWithoutPreload(cmd, [&output](const std::string& chunk) { output += chunk; });
        std::vector<Row> rows;
        std::istringstream lines {output};
        std::string line;
        while (std::getline(lines, line)) {
            std::vector<std::string> f;
            std::istringstream parts {line};
            std::string field;
            while (std::getline(parts, field, '|'))
                f.push_back(field);
            if (f.size() >= 6 && f[0] == "emu")
                rows.push_back({"emu", f[1], f[2], f[3], f[4] == "1", f[5]});
            else if (f.size() >= 4 && f[0] == "none")
                rows.push_back({"none", f[3], f[1], "", true, f[2]});
        }
        {
            std::unique_lock<std::mutex> lock {shared->mutex};
            shared->pending = rows;
        }
        shared->reading = false;
        shared->ready = true;
    }).detach();
}

int GuiEmulators::missingNeeded() const
{
    int n {0};
    for (const Row& r : mRows)
        n += (r.kind == "emu" && r.needed && r.state != "ready") ? 1 : 0;
    return n;
}

void GuiEmulators::showPlan()
{
    {
        std::unique_lock<std::mutex> lock {mShared->mutex};
        mRows = mShared->pending;
    }
    const int cursor {mList->size() > 0 ? mList->getCursorId() : 0};
    mList = std::make_shared<ComponentList>();
    const std::shared_ptr<Font> font {Font::get(FONT_SIZE_MEDIUM)};
    const std::shared_ptr<Font> small {Font::get(FONT_SIZE_SMALL)};
    const std::shared_ptr<Font> quiet {Font::get(FONT_SIZE_SMALL, FONT_PATH_LIGHT)};
    int needed {0};
    int ready {0};
    std::string firstNeeded;

    for (const Row& r : mRows) {
        if (r.kind == "emu" && r.needed) {
            if (needed == 0)
                firstNeeded = r.name;
            ++needed;
            ready += r.state == "ready" ? 1 : 0;
        }
        ComponentListRow row;
        const bool done {r.kind == "emu" && r.state == "ready"};
        auto icon = std::make_shared<ImageComponent>();
        icon->setResize(0.0f, std::round(font->getLetterHeight() * 1.6f));
        icon->setImage(done ? ":/graphics/setup/done.svg" : ":/graphics/setup/todo.svg");
        icon->setColorShift(done ? mMenuColorGreen : mMenuColorScrollIndicators);
        row.addElement(icon, false);
        auto spacer = std::make_shared<GuiComponent>();
        spacer->setSize(std::round(font->getLetterHeight() * 0.8f), 0.0f);
        row.addElement(spacer, false);

        std::string name {r.name};
        std::string detail {r.detail};
        std::string tag;
        bool loud {false};
        if (r.kind == "none") {
            const int count {std::atoi(r.detail.c_str())};
            const std::string games {Utils::String::format(_n("%i game", "%i games", count), count)};
            if (r.id == "deckhand") {
                name = _("Windows games");
                detail = games + " · " + _("Deckhand, Arcadia's sister app, plays these");
                tag = _("Get Deckhand");
                loud = true;
            }
            else {
                detail = games + " · " +
                         Utils::String::format(_("Arcadia uses %s, which isn't on Flathub"), r.id.c_str());
            }
        }
        else if (r.state == "ready") {
            tag = _("Installed");
        }
        else {
            tag = r.state == "cores" ? _("Add cores") : _("Install");
            loud = r.needed;
        }

        auto label = std::make_shared<TextComponent>(name, font, mMenuColorPrimary);
        std::shared_ptr<TextComponent> tagText;
        if (!tag.empty())
            tagText = std::make_shared<TextComponent>("  " + tag, small,
                                                      loud ? mMenuColorAccentInk : mMenuColorSecondary,
                                                      ALIGN_RIGHT);
        const float room {mList->getSize().x - std::round(56.0f * mRenderer->getScreenWidthModifier()) -
                          icon->getSize().x - spacer->getSize().x - label->getSize().x -
                          (tagText ? tagText->getSize().x : 0.0f) - font->getLetterHeight()};
        row.addElement(label, false);
        auto detailText = std::make_shared<TextComponent>("", quiet, mMenuColorSecondary, ALIGN_LEFT);
        detailText->setText("  ·  " + detail, true, std::max(room, 0.0f));
        row.addElement(detailText, true);
        if (tagText)
            row.addElement(tagText, false);
        const Row copy {r};
        row.makeAcceptInputHandler([this, copy] { choose(copy); });
        mList->addRow(row);
    }
    layout();
    if (cursor > 0 && mList->size() > 0)
        mList->moveCursor(std::min(cursor, static_cast<int>(mList->size()) - 1));
    mList->onFocusGained();

    const int left {needed - ready};
    if (mRows.empty())
        mSubline.setText(_("The emulator list couldn't be read. Try again from Setup."));
    else if (needed == 0)
        mSubline.setText(_("No games yet. Add some and Arcadia picks what they need, or install one yourself."));
    else if (left == 0)
        mSubline.setText(_("Everything your games need is installed. Have fun."));
    else if (needed == 1)
        mSubline.setText(Utils::String::format(
            _("Your games need %s, and it isn't ready yet. Press X to set it up."), firstNeeded.c_str()));
    else
        mSubline.setText(Utils::String::format(_n("Your games need %i emulators; %i isn't ready yet. Press X to set "
                                                  "them all up.",
                                                  "Your games need %i emulators; %i aren't ready yet. Press X to set "
                                                  "them all up.",
                                                  left),
                                               needed, left));
    updateHelpPrompts();
}

void GuiEmulators::choose(const Row& row)
{
    if (row.kind == "none") {
        if (row.id == "deckhand")
            runTool(_("Windows games"), "get-deckhand.sh");
        return;
    }
    if (row.state != "ready") {
        runTool(Utils::String::format(row.state == "cores" ? _("Adding cores for %s").c_str() :
                                                             _("Installing %s").c_str(),
                                      row.name.c_str()),
                "install-emulators.sh\" \"" + row.id);
        return;
    }
    const std::string id {row.id};
    const std::string name {row.name};
    mWindow->pushGui(new GuiMsgBox(
        name + " is installed. Update checks every installed emulator and its cores.", _("UPDATE"),
        [this] { runTool("Updating emulators", "update-emulators.sh"); }, _("REMOVE"),
        [this, id, name] {
            mWindow->pushGui(new GuiMsgBox(
                "Remove " + name + "? Your games, saves and settings stay.", _("REMOVE"),
                [this, id, name] {
                    runTool("Removing " + name, "install-emulators.sh\" --remove \"" + id);
                },
                _("CANCEL"), nullptr));
        },
        _("CANCEL"), nullptr));
}

void GuiEmulators::runTool(const std::string& title, const std::string& args)
{
    mWindow->pushGui(new GuiToolRunner(title, "bash \"" + mToolsDirectory + "/" + args + "\"",
                                       [this] { readPlan(); }));
}

void GuiEmulators::close()
{
    auto onClose = mOnClose;
    delete this;
    if (onClose)
        onClose();
}

void GuiEmulators::update(int deltaTime)
{
    if (mShared->ready) {
        mShared->ready = false;
        showPlan();
    }
    mList->update(deltaTime);
    GuiComponent::update(deltaTime);
}

void GuiEmulators::render(const glm::mat4& parentTrans)
{
    const glm::mat4 trans {parentTrans * getTransform()};
    renderChildren(trans);
    mList->render(trans);
}

bool GuiEmulators::input(InputConfig* config, Input input)
{
    if (input.value != 0 && (config->isMappedTo("b", input) || config->isMappedTo("left", input))) {
        close(); // (left goes back towards the settings rail, as B does)
        return true;
    }
    if (input.value != 0 && config->isMappedTo("x", input) && missingNeeded() > 0) {
        runTool(_("Installing what your games need"), "install-emulators.sh");
        return true;
    }
    if (input.value != 0 && config->isMappedTo("y", input) && !mRows.empty()) {
        runTool(_("Updating emulators"), "update-emulators.sh");
        return true;
    }
    return mList->input(config, input);
}

std::vector<HelpPrompt> GuiEmulators::getHelpPrompts()
{
    std::vector<HelpPrompt> prompts;
    prompts.push_back(HelpPrompt("up/down", _("choose")));
    prompts.push_back(HelpPrompt("a", _("install or manage")));
    if (missingNeeded() > 0)
        prompts.push_back(HelpPrompt("x", _("install what's needed")));
    prompts.push_back(HelpPrompt("y", _("update all")));
    prompts.push_back(HelpPrompt("b", _("back")));
    return prompts;
}
