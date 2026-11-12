//  SPDX-License-Identifier: MIT
//
//  Arcadia Frontend
//  MenuComponent.cpp
//
//  Basic component for building a menu.
//

#include "components/MenuComponent.h"

#include "Settings.h"
#include "components/ButtonComponent.h"

#define BUTTON_GRID_VERT_PADDING Font::get(FONT_SIZE_MEDIUM)->getLetterHeight() * 0.915f
#define BUTTON_GRID_HORIZ_PADDING Font::get(FONT_SIZE_MEDIUM)->getLetterHeight() * 0.9f

#define TITLE_HEIGHT                                                                               \
    (mTitle->getFont()->getLetterHeight() + (Renderer::getIsVerticalOrientation() ?                \
                                                 Renderer::getScreenWidth() * 0.0637f :            \
                                                 Renderer::getScreenHeight() * 0.0637f))

MenuComponent::MenuComponent(std::string title, const std::shared_ptr<Font>& titleFont)
    : mRenderer {Renderer::getInstance()}
    , mGrid {glm::ivec2 {2, 4}}
    , mNeedsSaving {false}
{
    addChild(&mBackground);
    addChild(&mGrid);

    // Set up title.
    mTitle = std::make_shared<TextComponent>();
    mTitle->setAutoCalcExtent(glm::ivec2 {0, 0});
    mTitle->setHorizontalAlignment(ALIGN_LEFT);
    mTitle->setColor(mMenuColorTitle);
    // A card next to the settings rail carries a smaller heading; the rail's title heads the screen.
    mCard = sRailOpen && !Renderer::getIsVerticalOrientation();
    setTitle(title, mCard ? Font::get(FONT_SIZE_LARGE * 0.74f, FONT_PATH_TITLE) : titleFont);
    mGrid.setEntry(mTitle, glm::ivec2 {0, 0}, false, true, glm::ivec2 {2, 2});

    // Set up list which will never change (externally, anyway).
    mList = std::make_shared<ComponentList>();
    mGrid.setEntry(mList, glm::ivec2 {0, 2}, true, true, glm::ivec2 {2, 1});

    // Set up scroll indicators.
    mScrollUp = std::make_shared<ImageComponent>();
    mScrollDown = std::make_shared<ImageComponent>();

    mScrollUp->setResize(0.0f, mTitle->getFont()->getLetterHeight() / 2.0f);
    mScrollUp->setOrigin(0.0f, -0.35f);

    mScrollDown->setResize(0.0f, mTitle->getFont()->getLetterHeight() / 2.0f);
    mScrollDown->setOrigin(0.0f, 0.35f);

    mScrollIndicator = std::make_shared<ScrollIndicatorComponent>(mList, mScrollUp, mScrollDown);

    mGrid.setEntry(mScrollUp, glm::ivec2 {1, 0}, false, false, glm::ivec2 {1, 1});
    mGrid.setEntry(mScrollDown, glm::ivec2 {1, 1}, false, false, glm::ivec2 {1, 1});

    updateGrid();
    updateSize();

    mGrid.resetCursor();
}

MenuComponent::~MenuComponent()
{
    // Save when destroyed.
    save();
}

void MenuComponent::save()
{
    if (!mSaveFuncs.size())
        return;

    for (auto it = mSaveFuncs.cbegin(); it != mSaveFuncs.cend(); ++it)
        (*it)();

    if (mNeedsSaving) {
        Settings::getInstance()->saveFile();
        mNeedsSaving = false;
    }
}

void MenuComponent::setTitle(std::string title, const std::shared_ptr<Font>& font)
{
    mTitle->setText(Utils::Localization::readable(title));
    mTitle->setFont(font);
}

float MenuComponent::getButtonGridHeight() const
{
    if (!mButtonGrid && (mRail || mCard))
        return std::round(mRenderer->getScreenHeight() * 0.02f);
    return (mButtonGrid ? mButtonGrid->getSize().y :
                          Font::get(FONT_SIZE_MEDIUM)->getSize() * 1.5f + BUTTON_GRID_VERT_PADDING);
}

void MenuComponent::updateSize()
{
    // Arcadia (DESIGN.md): every menu is a sheet down the left side of the screen, the full height
    // apart from a small margin, so the game or console you came from stays in view on the right.
    // The bottom margin leaves the button hints visible below the sheet. On the settings screen the
    // rail takes the left and the menus are cards beside it.
    const glm::vec2 margin {sheetMargin()};
    const float bottom {mRenderer->getScreenHeight() * 0.9f};
    if (mRail) {
        setSize(railWidth(), bottom - margin.y);
        return;
    }
    if (mCard) {
        const glm::vec3 pos {sheetPosition()};
        setSize(mRenderer->getScreenWidth() - pos.x - margin.x, bottom - pos.y);
        return;
    }
    const float height {bottom - margin.y};
    const float width {mRenderer->getIsVerticalOrientation() ?
                           mRenderer->getScreenWidth() - 2.0f * margin.x :
                           std::max(mRenderer->getScreenWidth() * 0.52f,
                                    std::min(mRenderer->getScreenHeight() * 0.95f,
                                             mRenderer->getScreenWidth() * 0.9f))};
    setSize(width, height);
}

glm::vec2 MenuComponent::sheetMargin()
{
    Renderer* renderer {Renderer::getInstance()};
    return glm::vec2 {std::round(renderer->getScreenWidth() * 0.034f),
                      std::round(renderer->getScreenHeight() * 0.04f)};
}

glm::vec3 MenuComponent::sheetPosition()
{
    const glm::vec2 margin {sheetMargin()};
    if (sRailOpen && !Renderer::getIsVerticalOrientation())
        return glm::vec3 {std::round(margin.x + railWidth() +
                                     Renderer::getInstance()->getScreenWidth() * 0.02f),
                          std::round(margin.y + headerHeight()), 0.0f};
    return glm::vec3 {margin.x, margin.y, 0.0f};
}

float MenuComponent::railWidth()
{
    return std::round(Renderer::getInstance()->getScreenWidth() * 0.235f);
}

float MenuComponent::headerHeight()
{
    return std::round(Renderer::getInstance()->getScreenHeight() * 0.1f);
}

void MenuComponent::setRailStyle()
{
    mRail = true;
    mCard = false;
    mBackground.setVisible(false);
    mList->setPillSelector(true);
    updateSize();
}

void MenuComponent::onSizeChanged()
{
    mBackground.fitTo(mSize);

    // Update grid row/column sizes. The rail's title is the screen header, so it gets the header's height.
    const float titleHeight {mRail ? headerHeight() : TITLE_HEIGHT};
    mGrid.setRowHeightPerc(0, titleHeight / mSize.y / 2.0f);
    mGrid.setRowHeightPerc(1, titleHeight / mSize.y / 2.0f);
    mGrid.setRowHeightPerc(3, getButtonGridHeight() / mSize.y);

    mGrid.setColWidthPerc(1, 0.055f);

    mGrid.setSize(mSize);

    // Cards keep their rows a little in from the edge so the focus ring has room; the rail runs flush.
    const float inset {mRail ? 0.0f : std::round(mRenderer->getScreenWidth() * 0.012f)};
    if (inset > 0.0f) {
        mList->setPosition(mList->getPosition().x + inset, mList->getPosition().y);
        mList->setSize(mList->getSize().x - inset * 2.0f, mList->getSize().y);
    }

    // The title sits on the left, lined up with the text of the rows below it, leaving room on the right
    // for the scroll indicators.
    const float indent {inset + std::round(28.0f * mRenderer->getScreenWidthModifier())};
    const float indicatorsSize {mSize.x * 0.09f};

    glm::vec2 titleSize {mTitle->getSize()};
    mTitle->setSize(titleSize.x - indicatorsSize - indent, titleSize.y);

    glm::vec3 titlePos {mTitle->getPosition()};
    mTitle->setPosition(titlePos.x + indent, titlePos.y, titlePos.z);
}

void MenuComponent::addButton(const std::string& name,
                              const std::string& helpText,
                              const std::function<void()>& callback)
{
    mButtons.push_back(std::make_shared<ButtonComponent>(name, helpText, callback));
    updateGrid();
    updateSize();
}

void MenuComponent::updateGrid()
{
    if (mButtonGrid)
        mGrid.removeEntry(mButtonGrid);

    mButtonGrid.reset();

    if (mButtons.size()) {
        mButtonGrid = makeButtonGrid(mButtons);
        mGrid.setEntry(mButtonGrid, glm::ivec2 {0, 3}, true, false, glm::ivec2 {2, 1});
    }
}

std::shared_ptr<ComponentGrid> MenuComponent::makeButtonGrid(
    const std::vector<std::shared_ptr<ButtonComponent>>& buttons)
{
    std::shared_ptr<ComponentGrid> buttonGrid {
        std::make_shared<ComponentGrid>(glm::ivec2 {static_cast<int>(buttons.size()), 2})};

    // Initialize to padding.
    float buttonGridWidth {BUTTON_GRID_HORIZ_PADDING * buttons.size()};

    for (int i = 0; i < static_cast<int>(buttons.size()); ++i) {
        buttonGrid->setEntry(buttons.at(i), glm::ivec2 {i, 0}, true, false);
        buttonGridWidth += buttons.at(i)->getSize().x;
    }
    for (unsigned int i = 0; i < buttons.size(); ++i)
        buttonGrid->setColWidthPerc(i, (buttons.at(i)->getSize().x + BUTTON_GRID_HORIZ_PADDING) /
                                           buttonGridWidth);

    buttonGrid->setSize(buttonGridWidth,
                        buttons.at(0)->getSize().y + BUTTON_GRID_VERT_PADDING + 2.0f);
    // Spacer row to deal with dropshadow to make buttons look centered.
    buttonGrid->setRowHeightPerc(1, 2.0f / buttonGrid->getSize().y);

    return buttonGrid;
}

std::shared_ptr<ImageComponent> MenuComponent::makeArrow()
{
    auto bracket = std::make_shared<ImageComponent>();
    bracket->setLinearInterpolation(true);
    bracket->setResize(0, Font::get(FONT_SIZE_MEDIUM)->getLetterHeight());
    bracket->setImage(":/graphics/arrow.svg");
    bracket->setColorShift(mMenuColorPrimary);
    return bracket;
}
