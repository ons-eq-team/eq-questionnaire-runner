#!/usr/bin/env python

import argparse
import json
import logging
import os
import re
from string import Template

from app.questionnaire.questionnaire_schema import QuestionnaireSchema

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser(
    description="Generate a bag of DOM selectors, organised by page, "
    "to make writing webdriver tests easier"
)

parser.add_argument(
    "SCHEMA",
    help="The path to the schema file you want to generate pages for."
    "If this path is a directory, then all files matching --test_schema_prefix"
    "will be used to generate pages",
)

parser.add_argument(
    "OUT_DIRECTORY",
    help="The path to the directory where the pages should be written."
    "If a schema directory is used, subdirectories will be created for each schema",
)

parser.add_argument(
    "-s",
    "--spec_file",
    help="The file where the template spec should be written."
    "This flag has no effect when using a schema directory",
)

parser.add_argument(
    "-r",
    "--require_path",
    default="../../base_pages",
    help="The relative path from a page file to the directory containing the base/parent page classes. "
    'Defaults to ".."',
)

SPEC_PAGE_HEADER = "const helpers = require('../helpers');\n\n"

SPEC_PAGE_IMPORT = Template(
    r"""const ${pageName}Page = require('../generated_pages/${pageDir}/${pageFile}');
"""
)

SPEC_EXAMPLE_TEST = Template(
    r"""
describe('Example Test', function() {
  beforeEach('Load the survey', function() {
    browser.openQuestionnaire('${schema}');
  });

  it('Given..., When..., Then...', function() {

  });
});

"""
)

HEADER = Template(
    r"""// >>> WARNING THIS PAGE WAS AUTO-GENERATED - DO NOT EDIT!!! <<<
const $basePage = require('$relativeRequirePath/$basePageFile');

"""
)

CLASS_NAME = Template(
    r"""class ${pageName}Page extends $basePage {

"""
)

QUESTION_DEFINITION_TITLE_GETTER = Template(
    r"""  definitionTitle${definitionIndex}() { return '.collapsible:nth-child(${definitionIndex}) > .collapsible__heading'; }

"""
)

QUESTION_DEFINITION_CONTENT_GETTER = Template(
    r"""  definitionContent${definitionIndex}() { return '.collapsible:nth-child(${definitionIndex}) > .collapsible__content'; }

"""
)

QUESTION_DEFINITION_BUTTON_GETTER = Template(
    r"""  definitionButton${definitionIndex}() { return '.collapsible:nth-child(${definitionIndex}) .js-collapsible-button'; }

"""
)

ANSWER_LABEL_GETTER = Template(
    r"""  ${answerName}Label() {
    return '[for=${answerId}]';
  }

"""
)

ANSWER_ERROR_GETTER = Template(
    r"""  ${answerName}ErrorItem() {
    return '[data-qa=error-body] div.panel__body > ul';
  }

"""
)

ANSWER_LABEL_DESCRIPTION_GETTER = Template(
    r"""  ${answerName}LabelDescription() { return 'label[for=${answerId}] > .label__description'; }

"""
)

ANSWER_GETTER = Template(
    r"""  ${answerName}() {
    return '#${answerId}';
  }

"""
)

BLOCK_DESCRIPTION = Template(
    r"""  ${block_name}Description() {
    return 'div.block__description';
  }

"""
)

ANSWER_UNIT_TYPE_GETTER = Template(
    r"""  ${answerName}Unit() {
    return '#${answerId}-type';
  }

"""
)

SECTION_SUMMARY_ANSWER_GETTER = Template(
    r"""  ${answerName}() { return '[data-qa="${answerId}"]'; }

"""
)

SECTION_SUMMARY_ANSWER_EDIT_GETTER = Template(
    r"""  ${answerName}Edit() { return '[data-qa="${answerId}-edit"]'; }

"""
)

SUMMARY_ANSWER_GETTER = Template(
    r"""  ${answerName}() { return '[data-qa="${answerId}"]'; }

"""
)


SUMMARY_ANSWER_EDIT_GETTER = Template(
    r"""  ${answerName}Edit() { return '[data-qa="${answerId}-edit"]'; }

"""
)

SUMMARY_TITLE_GETTER = Template(
    r"""  ${group_id_camel}Title() { return '#${group_id}'; }

"""
)

SUMMARY_SHOW_ALL_BUTTON = Template(
    r"""  summaryShowAllButton() { return '.js-collapsible-all'; }

"""
)

SUMMARY_QUESTION_GETTER = Template(
    r"""  ${questionName}() { return '[data-qa=${questionId}]'; }

"""
)

COLLAPSIBLE_SUMMARY_GETTER = r"""  collapsibleSummary() { return '#summary-accordion'; }

"""

CALCULATED_SUMMARY_LABEL_GETTER = Template(
    r"""  ${answerName}Label() { return '[data-qa=${answerId}-label]'; }

"""
)

LIST_SUMMARY_LABEL_GETTER = r"""  listLabel(instance) { return `tbody:nth-child(${instance}) td:first-child`; }

"""

LIST_SUMMARY_EDIT_LINK_GETTER = r"""  listEditLink(instance) { return `tbody:nth-child(${instance}) td:last-child a[data-qa='change-item-link']`; }

"""

LIST_SUMMARY_REMOVE_LINK_GETTER = r"""  listRemoveLink(instance) { return `tbody:nth-child(${instance}) td:last-child a[data-qa='remove-item-link']`; }

"""

LIST_SUMMARY_LIST_GETTER = r"""  listSummary() { return '.list__item'; }

"""

LIST_SECTION_SUMMARY_LABEL_GETTER = Template(
    r"""  ${list_name}ListLabel(listItemInstance) { return 'div[data-qa="${list_name}-list-summary"] tbody:nth-child(' + listItemInstance + ') td:first-child'; }

"""
)

LIST_SECTION_SUMMARY_ADD_LINK_GETTER = Template(
    r"""  ${list_name}ListAddLink() { return 'div[data-qa="${list_name}-list-summary"] a[data-qa="add-item-link"]'; }

"""
)

LIST_SECTION_SUMMARY_EDIT_LINK_GETTER = Template(
    r"""  ${list_name}ListEditLink(listItemInstance) { return 'div[data-qa="${list_name}-list-summary"] tbody:nth-child(' + listItemInstance + ') td:last-child a[data-qa="change-item-link"]'; }

"""
)

LIST_SECTION_SUMMARY_REMOVE_LINK_GETTER = Template(
    r"""  ${list_name}ListRemoveLink(listItemInstance) { return 'div[data-qa="${list_name}-list-summary"] tbody:nth-child(' + listItemInstance + ') td:last-child a[data-qa="remove-item-link"]'; }

"""
)

RELATIONSHIP_PLAYBACK_GETTER = r"""  playback() { return '[class*="relationships__playback"]'; }

"""

CLEAR_SELECTION_BUTTON_GETTER = r"""  clearSelectionButton() { return '.js-clear-btn'; }

"""

CONSTRUCTOR = Template(
    r"""  constructor() {
    super('${block_id}');
  }

"""
)

FOOTER = Template(
    r"""}
module.exports = new ${pageName}Page();
"""
)


def generate_pascal_case_from_id(id_str):
    parts = re.sub("[^0-9a-zA-Z]+", "-", id_str).split("-")
    name = "".join([p.title() for p in parts])
    return name


def camel_case(_string):
    if _string:
        return _string[0].lower() + _string[1:]


def get_all_questions(block):
    all_questions = []
    if block.get("question"):
        all_questions.append(block.get("question"))
    for question_variant in block.get("question_variants", []):
        if "question" in question_variant:
            all_questions.append(question_variant["question"])

    return all_questions


def process_options(answer_id, options, page_spec, base_prefix):
    for index, option in enumerate(options):
        if option["value"][0].isalpha():
            prefix = base_prefix
        else:
            prefix = base_prefix + "Answer"

        option_name = camel_case(prefix + generate_pascal_case_from_id(option["value"]))
        option_id = "{name}-{index}".format(name=answer_id, index=index)

        option_context = {"answerName": option_name, "answerId": option_id}

        page_spec.write(ANSWER_GETTER.substitute(option_context))
        page_spec.write(ANSWER_LABEL_GETTER.substitute(option_context))

        # Add a selector for an option which exposes another input, e.g.
        # an 'Other' option which exposes a text input for the user to fill in
        if "detail_answer" in option:
            option_context = {
                "answerId": option["detail_answer"]["id"],
                "answerName": option_name + "Detail",
            }
            page_spec.write(ANSWER_GETTER.substitute(option_context))


def process_answer(answer, page_spec, long_names, page_name):

    answer_name = generate_pascal_case_from_id(answer["id"])
    answer_name = answer_name.replace(page_name, "")
    answer_name = answer_name.replace("Answer", "")

    prefix = camel_case(answer_name) if answer_name and long_names else ""

    if answer_name is None or answer_name == "":
        answer_name = "answer"

    if answer["type"] in ("Radio", "Checkbox"):
        process_options(answer["id"], answer["options"], page_spec, prefix)
        if answer["type"] == "Radio":
            page_spec.write(CLEAR_SELECTION_BUTTON_GETTER)

    elif answer["type"] in "Relationship":
        process_options(answer["id"], answer["options"], page_spec, prefix)
        page_spec.write(RELATIONSHIP_PLAYBACK_GETTER)

    elif answer["type"] in "Date":
        page_spec.write(_write_date_answer(answer["id"], prefix))

    elif answer["type"] in "MonthYearDate":
        page_spec.write(_write_month_year_date_answer(answer["id"], prefix))

    elif answer["type"] in "Duration":
        page_spec.write(_write_duration_answer(answer["id"], answer["units"], prefix))

    elif answer["type"] in (
        "TextField",
        "Number",
        "TextArea",
        "Currency",
        "Percentage",
        "Unit",
        "Dropdown",
    ):
        answer_context = {
            "answerName": camel_case(answer_name),
            "answerId": answer["id"],
        }

        page_spec.write(ANSWER_GETTER.substitute(answer_context))
        page_spec.write(ANSWER_LABEL_GETTER.substitute(answer_context))
        page_spec.write(ANSWER_LABEL_DESCRIPTION_GETTER.substitute(answer_context))
        page_spec.write(ANSWER_ERROR_GETTER.substitute(answer_context))

        if answer["type"] == "Unit":
            page_spec.write(ANSWER_UNIT_TYPE_GETTER.substitute(answer_context))

    else:
        raise Exception("Answer type {} not configured".format(answer["type"]))


def process_question(question, page_spec, num_questions, page_name):
    long_names = long_names_required(question, num_questions)

    if "definitions" in question:
        for index, _ in enumerate(question["definitions"], 2):
            definition_context = {"definitionIndex": index}
            page_spec.write(
                QUESTION_DEFINITION_TITLE_GETTER.substitute(definition_context)
            )
            page_spec.write(
                QUESTION_DEFINITION_CONTENT_GETTER.substitute(definition_context)
            )
            page_spec.write(
                QUESTION_DEFINITION_BUTTON_GETTER.substitute(definition_context)
            )

    for answer in question.get("answers", []):
        process_answer(answer, page_spec, long_names, page_name)


def process_calculated_summary(answers, page_spec):
    for answer in answers:
        answer_name = generate_pascal_case_from_id(answer)
        answer_context = {"answerName": camel_case(answer_name), "answerId": answer}

        page_spec.write(SUMMARY_ANSWER_GETTER.substitute(answer_context))
        page_spec.write(SUMMARY_ANSWER_EDIT_GETTER.substitute(answer_context))
        page_spec.write(CALCULATED_SUMMARY_LABEL_GETTER.substitute(answer_context))


def process_summary(schema_data, page_spec, collapsible):
    for section in schema_data["sections"]:
        list_summaries = [
            summary_element
            for summary_element in section.get("summary", {}).get("items", [])
            if summary_element["type"] == "List"
        ]
        for list_block in list_summaries:
            list_context = {"list_name": list_block["for_list"]}
            page_spec.write(
                LIST_SECTION_SUMMARY_ADD_LINK_GETTER.substitute(list_context)
            )
            page_spec.write(
                LIST_SECTION_SUMMARY_EDIT_LINK_GETTER.substitute(list_context)
            )
            page_spec.write(
                LIST_SECTION_SUMMARY_REMOVE_LINK_GETTER.substitute(list_context)
            )
            page_spec.write(LIST_SECTION_SUMMARY_LABEL_GETTER.substitute(list_context))

    for section in schema_data["sections"]:
        for group in section["groups"]:
            for block in group["blocks"]:
                for question in get_all_questions(block):
                    question_context = {
                        "questionId": question["id"],
                        "questionName": camel_case(
                            generate_pascal_case_from_id(question["id"])
                        ),
                    }
                    for answer in question.get("answers", []):
                        answer_name = generate_pascal_case_from_id(answer["id"])
                        answer_context = {
                            "answerName": camel_case(answer_name),
                            "answerId": answer["id"],
                        }
                        if block["type"] == "SectionSummary":
                            page_spec.write(
                                SECTION_SUMMARY_ANSWER_GETTER.substitute(answer_context)
                            )
                            page_spec.write(
                                SECTION_SUMMARY_ANSWER_EDIT_GETTER.substitute(
                                    answer_context
                                )
                            )

                        page_spec.write(
                            SUMMARY_ANSWER_GETTER.substitute(answer_context)
                        )

                        page_spec.write(
                            SUMMARY_ANSWER_EDIT_GETTER.substitute(answer_context)
                        )

                    page_spec.write(
                        SUMMARY_QUESTION_GETTER.substitute(question_context)
                    )

                if block["type"] == "SectionSummary":
                    page_spec.write(SUMMARY_SHOW_ALL_BUTTON.substitute())

            if not collapsible:
                group_context = {
                    "group_id_camel": camel_case(
                        generate_pascal_case_from_id(group["id"])
                    ),
                    "group_id": group["id"],
                }
                page_spec.write(SUMMARY_TITLE_GETTER.substitute(group_context))

    if collapsible:
        page_spec.write(COLLAPSIBLE_SUMMARY_GETTER)


def long_names_required(question, num_questions):
    if num_questions > 1:
        return True

    num_answers = len(question.get("answers", []))
    if num_answers > 1:
        return True

    return False


def _write_date_answer(answer_id, prefix):
    return (
        ANSWER_GETTER.substitute(
            {"answerName": prefix + "day", "answerId": answer_id + "-day"}
        )
        + ANSWER_GETTER.substitute(
            {"answerName": prefix + "month", "answerId": answer_id + "-month"}
        )
        + ANSWER_GETTER.substitute(
            {"answerName": prefix + "year", "answerId": answer_id + "-year"}
        )
        + ANSWER_LABEL_GETTER.substitute(
            {"answerName": prefix + "day", "answerId": answer_id + "-day"}
        )
        + ANSWER_LABEL_GETTER.substitute(
            {"answerName": prefix + "month", "answerId": answer_id + "-month"}
        )
        + ANSWER_LABEL_GETTER.substitute(
            {"answerName": prefix + "year", "answerId": answer_id + "-year"}
        )
    )


def _write_month_year_date_answer(answer_id, prefix):
    return (
        ANSWER_GETTER.substitute(
            {"answerName": prefix + "Month", "answerId": answer_id + "-month"}
        )
        + ANSWER_GETTER.substitute(
            {"answerName": prefix + "Year", "answerId": answer_id + "-year"}
        )
        + ANSWER_LABEL_GETTER.substitute(
            {"answerName": prefix + "Month", "answerId": answer_id + "-month"}
        )
        + ANSWER_LABEL_GETTER.substitute(
            {"answerName": prefix + "Year", "answerId": answer_id + "-year"}
        )
    )


def _write_duration_answer(answer_id, units, prefix):
    resp = []
    for unit in units:
        resp.append(
            ANSWER_GETTER.substitute(
                {
                    "answerName": prefix + unit.title(),
                    "answerId": answer_id + "-" + unit,
                }
            )
        )

    return "".join(resp)


def find_kv(block, key, values):
    for question in get_all_questions(block):
        for answer in question.get("answers", []):
            if key in answer and answer[key] in values:
                return True

    return False


def process_block(
    block, dir_out, schema_data, spec_file, relative_require="..", page_filename=None
):
    logger.debug("Processing Block: %s", block["id"])

    if not page_filename:
        page_filename = block["id"] + ".page.js"

    if block["type"] == "ListCollector":
        list_operations = ["add", "edit", "remove"]
        for list_operation in list_operations:
            process_block(
                block[f"{list_operation}_block"],
                dir_out,
                schema_data,
                spec_file,
                relative_require,
                page_filename=f'{block["id"]}-{list_operation}.page.js',
            )

    if block["type"] == "PrimaryPersonListCollector":
        process_block(
            block["add_or_edit_block"],
            dir_out,
            schema_data,
            spec_file,
            relative_require,
            page_filename=f'{block["id"]}-add.page.js',
        )

    page_path = os.path.join(dir_out, page_filename)

    logger.info("creating %s...", page_path)

    with open(page_path, "w") as page_spec:
        page_name = generate_pascal_case_from_id(block["id"])

        base_page = "QuestionPage"
        base_page_file = "question.page"

        if block["type"] == "CalculatedSummary":
            base_page = "CalculatedSummaryPage"
            base_page_file = "calculated-summary.page"

        if block["type"] == "Introduction":
            base_page = "IntroductionPageBase"
            base_page_file = "introduction.page"

        block_context = {
            "pageName": page_name,
            "basePage": base_page,
            "basePageFile": base_page_file,
            "pageDir": dir_out.split("/")[-1],
            "pageFile": page_filename,
            "block_id": block["id"],
            "block_name": camel_case(generate_pascal_case_from_id(block["id"])),
            "relativeRequirePath": relative_require,
        }

        page_spec.write(HEADER.substitute(block_context))
        page_spec.write(CLASS_NAME.substitute(block_context))
        page_spec.write(CONSTRUCTOR.substitute(block_context))
        if block["type"] in ("Summary", "SectionSummary"):
            collapsible = block.get("collapsible", False)
            process_summary(schema_data, page_spec, collapsible)
        elif block["type"] == "CalculatedSummary":
            process_calculated_summary(
                block["calculation"]["answers_to_calculate"], page_spec
            )
        else:
            if block.get("description"):
                page_spec.write(BLOCK_DESCRIPTION.substitute(block_context))

            all_questions = get_all_questions(block)
            num_questions = len(all_questions)

            for question in all_questions:
                process_question(question, page_spec, num_questions, page_name)

        if block["type"] == "ListCollector":
            page_spec.write(LIST_SUMMARY_LABEL_GETTER)
            page_spec.write(LIST_SUMMARY_EDIT_LINK_GETTER)
            page_spec.write(LIST_SUMMARY_REMOVE_LINK_GETTER)
            page_spec.write(LIST_SUMMARY_LIST_GETTER)

        page_spec.write(FOOTER.substitute(block_context))

        if spec_file:
            with open(spec_file, "a") as required_template_spec:
                required_template_spec.write(SPEC_PAGE_IMPORT.substitute(block_context))


def process_schema(in_schema, out_dir, spec_file, require_path=".."):

    try:
        data = json.loads(open(in_schema).read())
    except Exception as ex:
        logger.error("error reading %s", in_schema)
        return

    try:
        os.stat(out_dir)
    except IndexError:
        os.mkdir(out_dir)

    for section in data["sections"]:
        for group in section["groups"]:
            for block in group["blocks"]:
                process_block(block, out_dir, data, spec_file, require_path)


if __name__ == "__main__":
    args = parser.parse_args()

    template_spec_file = args.spec_file

    os.makedirs(args.OUT_DIRECTORY, exist_ok=True)

    if template_spec_file:
        os.makedirs(os.path.dirname(template_spec_file), exist_ok=True)
        with open(template_spec_file, "w") as template_spec:
            template_spec.write(SPEC_PAGE_HEADER)
            template_spec.close()

            process_schema(
                args.SCHEMA, args.OUT_DIRECTORY, template_spec_file, args.require_path
            )

            with open(template_spec_file, "a") as template_spec:
                schema_name = {"schema": os.path.basename(args.SCHEMA)}
                template_spec.write(SPEC_EXAMPLE_TEST.substitute(schema_name))
    else:
        if os.path.isdir(args.SCHEMA):
            for root, dirs, files in os.walk(args.SCHEMA):
                for file in [os.path.join(root, file) for file in files]:
                    filename = os.path.basename(file)
                    logger.info("File %s", filename)
                    if filename[0] == ".":
                        continue
                    output_dir = os.path.join(
                        args.OUT_DIRECTORY, filename.split(".")[0].replace("test_", "")
                    )
                    if not os.path.exists(output_dir):
                        os.makedirs(output_dir)
                    process_schema(file, output_dir, None, args.require_path)

        else:
            process_schema(
                args.SCHEMA, args.OUT_DIRECTORY, template_spec_file, args.require_path
            )
